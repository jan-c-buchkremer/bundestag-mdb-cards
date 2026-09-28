"""Downscale the foundation's portrait downloads to `out/fotos/<person_id>.jpg`.

The daily build must stay fast, so a small manifest in the output folder remembers which source file (path, size,
mtime) each photo was made from; only new or changed sources are decoded again."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

WIDTH = 240  # the card shows 76 px wide (2x for sharp screens, and room for a larger layout); the index 28 px
QUALITY = 80
MANIFEST = ".manifest.json"
# bump when the output changes for the same source (size, quality, crop), so every photo is made again
VERSION = 1


def raw_dir() -> Path:
    """The foundation's raw folder that `person_photo.local_path` is relative to: BDF_RAW, else `raw/` next to the
    store (`data/raw` in the foundation repo, `/foundation/raw` in the container)."""
    if os.environ.get("BDF_RAW"):
        return Path(os.environ["BDF_RAW"])
    return Path(os.environ.get("BDF_DB", "../bundestag-data-foundation/data/bundestag.sqlite")).parent / "raw"


def _stamp(src: Path, rel: str) -> list:
    st = src.stat()
    return [VERSION, rel, st.st_size, st.st_mtime_ns]


def downscale(src: Path, dest: Path) -> None:
    with Image.open(src) as im:
        im.draft("RGB", (WIDTH, WIDTH))  # JPEG: decode at 1/2, 1/4 or 1/8 scale, at least WIDTH wide; much faster
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            flat = Image.new("RGB", im.size, (255, 255, 255))
            flat.paste(im, mask=im.getchannel("A"))
            im = flat
        else:
            im = im.convert("RGB")
        if im.width > WIDTH:
            im = im.resize((WIDTH, round(im.height * WIDTH / im.width)), Image.Resampling.LANCZOS)
        tmp = dest.with_suffix(".tmp")
        im.save(tmp, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        tmp.replace(dest)


def write_photos(sources: dict[str, str], raw: Path, out: Path) -> tuple[set[str], int]:
    """Make `out/<id>.jpg` for each person id -> `local_path` under `raw`. Returns the ids that have a photo and
    how many were (re-)encoded. Photos of ids no longer in `sources` are removed."""
    out.mkdir(parents=True, exist_ok=True)
    try:
        manifest = json.loads((out / MANIFEST).read_text())
    except (OSError, ValueError):
        manifest = {}
    done: dict[str, list] = {}
    todo: dict[str, tuple[Path, Path]] = {}
    for pid, rel in sorted(sources.items()):
        src = raw / rel
        dest = out / f"{pid}.jpg"
        if not src.is_file():
            continue
        done[pid] = _stamp(src, rel)
        if manifest.get(pid) != done[pid] or not dest.exists():
            todo[pid] = (src, dest)

    def make(pid: str) -> str | None:
        src, dest = todo[pid]
        try:
            downscale(src, dest)
        except (OSError, ValueError, Image.DecompressionBombError) as e:
            print(f"photo {pid}: cannot read {src}: {e}")
            dest.unlink(missing_ok=True)
            return pid
        return None

    # Pillow releases the GIL while decoding and encoding, so threads use every core
    with ThreadPoolExecutor() as pool:
        for failed in pool.map(make, todo):
            if failed:
                del done[failed]
    encoded = sum(1 for pid in todo if pid in done)
    for f in out.glob("*.jpg"):
        if f.stem not in done:
            f.unlink()
    (out / MANIFEST).write_text(json.dumps(done, ensure_ascii=False, indent=0))
    return set(done), encoded
