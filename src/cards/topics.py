"""Topics (docs/plan.md section 11.6, D19): `themen/index.html` and `themen/<theme id>.html`, one page per period
theme of the Themenlandschaft, read from `speech_themes.json` (LANDSCAPE_THEMES, as debate.py). Built only when the
file is set; the landscape owns topic modelling (D3).

Week clusters are not entities, their ids change with every rebuild of a week. The period theme's id is not stable
either: the landscape numbers themes by size and recomputes the model whenever the set of speeches changes. So the
pages say that their address may change, and no stubs are written for them; stable ids are a landscape requirement.
A topic page is an entity page: the theme's speeches (facts.py), the fractions that spoke on it, and the Vorgänge
whose debates they belong to."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from cards import facts, urls
from cards.ui import FOOTER, LANDSCAPE, crumbs, dot, e, entity_header, facet, frac_link, fraction_order, n, shell

SPEECHES = 100  # newest speeches of a theme in the page (a theme holds a few hundred)
NOTE = ("Themen stammen aus der Themenlandschaft, die alle Reden der Wahlperiode nach Ähnlichkeit gruppiert. Die "
        "Nummer eines Themas kann sich ändern, wenn neue Sitzungswochen hinzukommen; Links auf diese Seite sind "
        "deshalb nicht dauerhaft.")  # fmt: skip


def by_theme(themes: dict[str, dict], speeches: list[dict]) -> dict[int, dict]:
    """{theme id: {"id", "label", "speeches"}} for the speeches with a card, oldest first."""
    out: dict[int, dict] = {}
    for sp in speeches:
        t = themes.get(sp["id"])
        if t is None or t.get("theme_id") is None:
            continue
        th = out.setdefault(t["theme_id"], {"id": t["theme_id"], "label": t["label"], "speeches": []})
        th["speeches"].append(sp)
    return dict(sorted(out.items(), key=lambda kv: -len(kv[1]["speeches"])))


def topic_page(th: dict, procedures: dict[str, dict]) -> str:
    sps = th["speeches"]
    newest = sorted(sps, key=lambda s: (s["date"], s["id"]), reverse=True)[:SPEECHES]
    more = (f'<p class="explain">Die neuesten {n(len(newest))} von {n(len(sps))}. Alle: '
            f'<a href="{LANDSCAPE}index.html#thema={e(th["id"])}">das Thema in der Themenlandschaft ↗</a>.</p>'
            if len(sps) > len(newest) else "")  # fmt: skip
    per = Counter(s.get("fraction") or "ohne Fraktion" for s in sps)
    rows = "".join(f'<tr><td>{dot(f)} {frac_link(f)}</td><td class="num">{n(k)}</td></tr>'
                   for f, k in sorted(per.items(), key=lambda kv: fraction_order(kv[0])))  # fmt: skip
    vs = Counter(v for s in sps for v in procedures.get(s["id"], []))
    vlinks = "".join(f'<li><a href="../{e(urls.vorgang(v))}">{e(title)}</a> <span class="faint">'
                     f"{n(k)} {'Rede' if k == 1 else 'Reden'}</span></li>"
                     for (v, title), k in sorted(vs.items(), key=lambda kv: (-kv[1], kv[0][1])))  # fmt: skip
    body = (
        crumbs(("index.html", "Themen"), (None, th["label"]))
        + entity_header(th["label"], [f"{n(len(sps))} Reden in der 21. Wahlperiode", NOTE],
                        [f'<a href="{LANDSCAPE}index.html#thema={e(th["id"])}">In der Themenlandschaft ↗</a>'],
                        when="Thema")
        + facet("fraktionen", "Fraktionen", '<div class="rows"><table class="plenum"><thead><tr><th>Fraktion</th>'
                f"<th>Reden</th></tr></thead><tbody>{rows}</tbody></table></div>", explain="Wie viele Reden zu "
                "diesem Thema aus jeder Fraktion kamen; größere Fraktionen reden mehr.")
        + facet("reden", "Reden", facts.speech_list(newest, "../", "reden", note=more), len(sps))
        + facet("abstimmungen", "Abstimmungen und Beschlüsse",
                f'<ul class="plain">{vlinks}</ul>' if vlinks else "", len(vs), "Ein Thema gilt für Reden, nicht für "
                "Abstimmungen. Die Vorgänge, in deren Beratung die Reden gehalten wurden, führen zu ihren "
                "Abstimmungen.")
        + facet("drucksachen", "Drucksachen", "", explain="Drucksachen haben kein Thema der Themenlandschaft; das DIP "
                "ordnet sie nach Sachgebieten, die bei jedem Vorgang stehen.")
        + f"<footer>{FOOTER}</footer>"
    )  # fmt: skip
    return shell(root="../", kind="p-topic", active="debate", title=f"Thema: {th['label']}",
                 desc=f"Das Thema „{th['label']}“ im 21. Bundestag: Reden, Fraktionen und Vorgänge.", body=body,
                 data={"kind": "topic", "id": th["id"]}, head='<meta name="robots" content="noindex">')  # fmt: skip


def index_page(themes: dict[int, dict]) -> str:
    rows = "".join(
        f'<a class="row" href="{e(th["id"])}.html"><span class="t"><span class="ti">{e(th["label"])}</span></span>'
        f'<span class="l">{n(len(th["speeches"]))} Reden</span></a>'
        for th in themes.values()
    )
    body = ('<h1>Themen</h1><p class="lead">Die Themen der 21. Wahlperiode aus der Themenlandschaft, das größte '
            f'zuerst. {NOTE}</p><div class="rows">{rows}</div><footer>{FOOTER}</footer>')  # fmt: skip
    return shell(root="../", kind="p-topics", active="debate", title="Themen der Wahlperiode",
                 desc="Die Themen der Reden im 21. Deutschen Bundestag, aus der Themenlandschaft.", body=body,
                 data={"kind": "topics"}, head='<meta name="robots" content="noindex">')  # fmt: skip


def write(out: Path, themes: dict[str, dict], speeches: list[dict], sittings: list[dict]) -> dict[int, dict]:
    """Write themen/ when the landscape's themes are there; returns the themes written (empty without them)."""
    grouped = by_theme(themes, speeches)
    if not grouped:
        return {}
    procedures: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for s in sittings:
        for i in s["items"]:
            for part in [i, *(i.get("sub_items") or [])]:
                for sp in part["speeches"]:
                    procedures[sp["id"]] += [(v["id"], v["title"]) for v in part.get("vorgaenge") or []]
    d = out / "themen"
    d.mkdir(parents=True, exist_ok=True)
    for th in grouped.values():
        (d / f"{th['id']}.html").write_text(topic_page(th, procedures), encoding="utf-8")
    (d / "index.html").write_text(index_page(grouped), encoding="utf-8")
    return grouped
