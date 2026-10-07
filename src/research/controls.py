"""Visual controls (docs/plan.md, goal 3): the reader picks by seeing. The data itself is the control: a tile per
Sachgebiet, a chip per fraction, the stages of a bill's way through the procedure, a bar per kind of Vorgang and a bar
per week. Every chart is also a filter, the filters combine, and the list below shows what they leave.

Drawn here, in Python at build time, as HTML with the sizes inline: static, no layout shift, no chart library, like
the hemicycle. Every clickable part is a real button (or a link where it opens a page), so the charts work with the
keyboard and a screen reader. One small module, `controls.js`, makes them interactive for every page:

- a page has one scope (`scope`): the controls, the toolbar (search, the active filters, "zurücksetzen") and the
  list (`rows`), whose rows carry their values as data attributes (`data-art`, `data-stufe`, `data-von`, `data-w`
  for the ISO week of the row's date, …; several values separated by spaces);
- a button with `data-f="<key>" data-v="<value>"` toggles that value (`aria-pressed`); values of one key are
  alternatives, keys combine;
- the state lives in the URL fragment (`#art=antrag&von=cdu,spd&zeit=2026-W10..2026-W20&q=miete&ansicht=stufe`), so a
  view can be shared and the back button works; a fragment without "=" is an anchor and stays one;
- each chart has a switch to its list or table (`view`), remembered as `ansicht=<chart>` in the fragment;
- without JavaScript the page shows every chart, its table and the full list.

Sizes and order come from counts only (docs/plan.md, non-goals: no rankings of people, no ratings). Colours: the
accent for a neutral selection, the fraction colours only for fractions, the result colours only for results."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from collections.abc import Iterable

from research.data import iso_week
from research.ui import MONTHS, e, n

LIMIT = 30  # rows of a long list shown at first; "mehr anzeigen" shows the next ones
KIND_CLASSES = 5  # the neutral shades of the kinds (k1 … k5); later kinds share the last one
# the groups of Einbringer as chips (data.initiator_group): the six fractions, the Bundesregierung, Bundesrat und
# Länder, Sonstige. The token is the filter value and the colour (shell.css): a fraction's colour for a fraction, the
# government's slate, neutral ones for the rest
GROUP_TOKENS = {
    "AfD": "afd", "CDU/CSU": "cdu", "BÜNDNIS 90/DIE GRÜNEN": "gru", "SPD": "spd", "Die Linke": "lin",
    "fraktionslos": "frl", "Bundesregierung": "reg", "Bundesrat und Länder": "laender", "Sonstige": "sonstige",
}  # fmt: skip
SHORT = {"BÜNDNIS 90/DIE GRÜNEN": "Grüne"}
DATIVE = {"Vorgänge": "Vorgängen", "Beschlüsse": "Beschlüssen", "Einträge": "Einträgen"}  # "12 von 300 Vorgängen"
HEAD = '<script>document.documentElement.classList.add("js")</script>'


def head(root: str) -> str:
    """What a page with controls puts into <head>: the "js" class before the first paint (so the list and table
    views do not flash), and controls.js."""
    return f'{HEAD}<script src="{root}controls.js" defer></script>'


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}".rstrip("0").rstrip(".") if whole else "0"


def share(part: int, whole: int) -> str:
    """A share in German, "12 %", "0,4 %" for the small ones."""
    if not whole:
        return "0 %"
    p = 100 * part / whole
    return (f"{p:.0f}" if p >= 1 or p == 0 else f"{p:.1f}".replace(".", ",")) + " %"


def _count(k: int) -> str:
    """A count that controls.js rewrites when other filters are active ("12 von 57")."""
    return f'<span class="c" data-n="{k}">{n(k)}</span>'


def toggle(key: str, value: str, inner: str, *, cls: str = "", style: str = "", label: str = "", name: str = "",
           disabled: bool = False, tab: bool = True, single: bool = False, also: str = "") -> str:  # fmt: skip
    """A toggle button of a filter value. `label` is the value's name for the active-filter line; `name` the
    accessible name of a button without text (a bar segment), also its tooltip. `single`: the key holds one value
    and chooses what the list is; `also`: "key=value" chosen with it (a chart of the Kleine Anfragen chooses that
    list)."""
    attrs = [
        f'type="button" class="{("tg " + cls).strip()}" data-f="{e(key)}" data-v="{e(value)}"',
        'aria-pressed="false"',
    ]
    if label:
        attrs.append(f'data-label="{e(label)}"')
    if name:
        attrs.append(f'aria-label="{e(name)}" title="{e(name)}"')
    if style:
        attrs.append(f'style="{style}"')
    if disabled:
        attrs.append("disabled")
    if not tab:
        attrs.append('tabindex="-1"')
    if single:
        attrs.append("data-single")
    if also:
        attrs.append(f'data-set="{e(also)}"')
    return f"<button {' '.join(attrs)}>{inner}</button>"


def scope(body: str, noun: str, one: str, attrs: dict[str, str] | None = None) -> str:
    """The part of a page the controls work on: `noun` and `one` name its rows in the count ("Vorgänge",
    "Vorgang", and in the dative after "von" from DATIVE); `attrs` maps a filter key to the row attribute it reads
    when they differ ({"art": "kind"})."""
    extra = "".join(f' data-attr-{e(k)}="{e(v)}"' for k, v in (attrs or {}).items())
    return (
        f'<div class="ctl-scope" data-noun="{e(noun)}" data-one="{e(one)}" data-dat="{e(DATIVE.get(noun, noun))}"'
        f"{extra}>{body}</div>"
    )  # fmt: skip


def toolbar(placeholder: str) -> str:
    """The search field, the active filters and the one "zurücksetzen" of a scope."""
    return (
        '<div class="ctl-bar"><input type="search" data-q placeholder="' + e(placeholder) + '" autocomplete="off" '
        f'aria-label="{e(placeholder.rstrip(" …"))}"><span class="ctl-sum" data-summary aria-live="polite"></span>'
        '<button type="button" class="reset" data-reset disabled>zurücksetzen</button></div>'
    )


def rows(rows_html: Iterable[str], key: str, empty: str, row: str = "", cls: str = "rows") -> str:
    """The list a scope filters, every row in the file (the full list without JavaScript); controls.js shows the
    first LIMIT of the filter result and "mehr anzeigen" for the next ones. `row`: the selector of a row when the
    rows sit in groups (`data-group`, hidden when none of their rows is left)."""
    body = "".join(rows_html)
    if not body:
        return f'<div class="rows"><div class="empty">{e(empty)}</div></div>'
    sel = f' data-row="{e(row)}"' if row else ""
    return (
        f'<div class="count" data-count></div><div class="{cls}" id="{e(key)}" data-rows{sel} data-limit="{LIMIT}">'
        f'{body}<div class="empty" data-none hidden>Keine Treffer für diese Auswahl.</div>'
        '<button type="button" class="more" data-more hidden>mehr anzeigen</button></div>'
    )


def view(key: str, title: str, chart: str, alt: str | None, alt_label: str = "Als Tabelle") -> str:
    """A chart with its list or table one click away; without JavaScript both are shown. `alt` None: the chart's
    own elements are the list, laid out as one (the tile field of the Gremien, `.cv.alt .tiles`)."""
    if alt is None:
        return (
            f'<figure class="cv relayout" data-view="{e(key)}"><figcaption class="cv-cap"><span class="cv-t">{e(title)}'
            '</span><span class="cv-sw" role="group" aria-label="Darstellung">'
            '<button type="button" data-show="chart" aria-pressed="true">Diagramm</button>'
            f'<button type="button" data-show="alt" aria-pressed="false">{e(alt_label)}</button></span></figcaption>'
            f"{chart}</figure>"
        )
    return (
        f'<figure class="cv" data-view="{e(key)}"><figcaption class="cv-cap"><span class="cv-t">{e(title)}</span>'
        '<span class="cv-sw" role="group" aria-label="Darstellung">'
        '<button type="button" data-show="chart" aria-pressed="true">Diagramm</button>'
        f'<button type="button" data-show="alt" aria-pressed="false">{e(alt_label)}</button></span></figcaption>'
        f'<div class="cv-chart">{chart}</div><div class="cv-alt">{alt}</div></figure>'
    )


def block(title: str, body: str) -> str:
    """A control without a chart of its own (chips), titled like a chart."""
    return f'<div class="cv"><div class="cv-cap"><span class="cv-t">{e(title)}</span></div>{body}</div>'


def table(head: list[str], body: list[list[str]], cls: str = "") -> str:
    """A plain table of counts for a chart's "Als Tabelle" (cells are HTML; the first column left-aligned)."""
    th = "".join(f"<th>{h}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f'<td{' class="num"' if i else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>"
                 for r in body)  # fmt: skip
    return (f'<div class="rows scroll"><table class="plenum {cls}"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody>'
            "</table></div>")  # fmt: skip


# ---------------------------------------------------------------- the components


def kind_class(i: int) -> str:
    return f"k{min(i, KIND_CLASSES - 1) + 1}"


def segmented(key: str, items: list[tuple], title: str, noun: str, also: str = "") -> str:
    """One bar, a segment per kind (value, label, count, and a colour token for a fraction), width by share, in the
    order given (largest first); a key below names each kind with its count and share. A segment and its key entry
    toggle the same value; the key is the keyboard's way (a narrow segment is hard to hit). A pressed segment is the
    accent, or, in a fraction's colour, outlined."""
    total = sum(x[2] for x in items)
    segs, keys = [], []
    for i, (value, label, k, *colour) in enumerate(items):
        if not k:
            continue
        cls = "own" if colour else kind_class(i)
        bg = f";--c:var(--{colour[0]})" if colour else ""
        segs.append(toggle(key, value, "", cls=f"seg-s {cls}", style=f"flex-grow:{k}{bg}", tab=False, label=label,
                           name=f"{label}: {n(k)} {noun}, {share(k, total)}", also=also))  # fmt: skip
        inner = (f'<i class="sw {cls}"{f' style="{bg[1:]}"' if bg else ""}></i>{e(label)} {_count(k)} '
                 f'<span class="p">{share(k, total)}</span>')  # fmt: skip
        keys.append(toggle(key, value, inner, cls="key", label=label, also=also))
    return (
        f'<div class="seg" role="group" aria-label="{e(title)}"><div class="seg-bar">{"".join(segs)}</div>'
        f'<div class="seg-key">{"".join(keys)}</div></div>'
    )


def segmented_table(items: list[tuple], head: str, noun: str) -> str:
    total = sum(x[2] for x in items)
    return table([e(head), e(noun), "Anteil"], [[e(x[1]), n(x[2]), share(x[2], total)] for x in items if x[2]])


def pipeline(key: str, stages: list[tuple[str, str, int]], ended: list[tuple[str, str, int]], title: str,
             ended_title: str = "", rest: tuple[str, str, int] | None = None) -> str:  # fmt: skip
    """The way through a procedure: the stages (value, label, count) in order, each with the number of items that
    stand there now and a bar by that number; below, the branch of the items that ended there (`ended`), and `rest`
    (items without a known stage) when it has any. Each stage toggles its value."""
    most = max([k for *_, k in stages + ended] + [1])

    def stage(value: str, label: str, k: int, cls: str) -> str:
        bar = f'<i class="pb" style="width:{_pct(k, most)}%"></i>'
        return toggle(key, value, f'<span class="pl">{e(label)}</span>{_count(k)}{bar}', cls=cls, label=label)

    main = "".join(f"<li>{stage(v, label, k, 'stage')}</li>" for v, label, k in stages)
    branch = "".join(stage(v, label, k, "stage end") for v, label, k in ended)
    extra = stage(*rest, "stage rest") if rest and rest[2] else ""
    end = (f'<div class="pipe-end">{f"<span class=k>{e(ended_title)}</span>" if branch else ""}{branch}{extra}</div>'
           if branch or extra else "")  # fmt: skip
    return f'<div class="pipe" role="group" aria-label="{e(title)}"><ol class="pipe-main">{main}</ol>{end}</div>'


def sized_chips(key: str, items: list[tuple[str, str, int]], title: str, also: str = "") -> str:
    """Toggle chips (value, label, count) in a neutral colour, largest first, each with a bar by its count against
    the largest: for groups that have no colour of their own, such as committees."""
    most = max([k for *_, k in items] + [1])
    out = "".join(toggle(key, value, f'{e(label)} {_count(k)}<i class="cb" style="width:{_pct(k, most)}%"></i>',
                         cls="chip sized", label=label, also=also) for value, label, k in items)  # fmt: skip
    return f'<div class="chips ctl-chips" role="group" aria-label="{e(title)}">{out}</div>'


def chips(key: str, items: list[tuple[str, str, int, str]], title: str, also: str = "") -> str:
    """Toggle chips (value, label, count, colour token), several at once; a chip without anything to filter is
    disabled. The colour is the fraction's (or the government's, a neutral one for the rest), the name and the
    count stand in text."""
    out = []
    for value, label, k, colour in items:
        out.append(toggle(key, value, f'<i class="dot"></i>{e(label)} {_count(k)}', cls="chip",
                          style=f"--c:var(--{colour})", label=label, disabled=not k, also=also))  # fmt: skip
    return f'<div class="chips ctl-chips" role="group" aria-label="{e(title)}">{"".join(out)}</div>'


def group_chips(key: str, counts: Counter, title: str = "Einbringer") -> str:
    """The Einbringer as chips: the six fractions, the Bundesregierung, Bundesrat und Länder and Sonstige, each with
    its count (`counts` by group name, data.initiator_group)."""
    items = [(tok, SHORT.get(g, g), counts[g], tok) for g, tok in GROUP_TOKENS.items()
             if g != "fraktionslos" or counts[g]]  # fmt: skip
    return chips(key, items, title)


def stacked(key: str, groups: list[tuple[str, str, str, Counter]], kinds: list[tuple], title: str,
            noun: str, also: str = "") -> str:  # fmt: skip
    """One row per group (value, label, colour token, counts by kind), the segments per kind (`kinds`: (kind,
    label) in the kinds' neutral shades, or (kind, label, colour token), e.g. the fractions), the length by the
    group's total against the largest; the numbers in the row's text and on each segment's tooltip. A row toggles its
    group; `also` chooses a list with it."""
    most = max([sum(c.values()) for *_, c in groups] + [1])
    out = []
    for value, label, colour, c in groups:
        total = sum(c.values())
        own = [(k[0], k[1], colour) for k in kinds] if len(kinds) == 1 and len(kinds[0]) == 2 else kinds  # one kind
        segs = "".join(
            f'<i {_shade(i, kind)} style="flex-grow:{c[kind[0]]}{_bg(kind)}" title="{e(kind[1])}: {n(c[kind[0]])}"></i>'
            for i, kind in enumerate(own)
            if c[kind[0]]
        )
        text = " · ".join(f"{n(c[k[0]])} {e(k[1])}" for k in kinds if c[k[0]]) if len(kinds) > 1 else ""
        inner = (f'<span class="sn"><i class="dot" style="background:var(--{colour})"></i>{e(label)}</span>'
                 f'<span class="sb"><span class="sbar" style="width:{_pct(total, most)}%">{segs}</span></span>'
                 f'<span class="stot">{_count(total)}</span><span class="sx">{text}</span>')  # fmt: skip
        out.append(toggle(key, value, inner, cls="srow", label=label, also=also))
    legend = "".join(f'<span><i {_shade(i, k, "sw")} style="{_bg(k)[1:]}"></i>{e(k[1])}</span>'
                     for i, k in enumerate(kinds)) if len(kinds) > 1 else ""  # fmt: skip
    return (f'<div class="stack" role="group" aria-label="{e(title)}">'
            f'{f"<div class=legend>{legend}</div>" if legend else ""}{"".join(out)}</div>')  # fmt: skip


def _shade(i: int, kind: tuple, cls: str = "") -> str:
    """The class of a kind's segment: its neutral shade, or none when the kind brings its own colour."""
    return f'class="{" ".join(x for x in (cls, "" if len(kind) > 2 else kind_class(i)) if x)}"'


def _bg(kind: tuple) -> str:
    return f";background:var(--{kind[2]})" if len(kind) > 2 else ""


ROW_WIDTH = 770  # px, the width of the tile field on a wide screen (main's content width)
TILE_ROWS = 6  # about this many rows of tiles on a wide screen
TILE_MIN = 150  # px, the narrowest tile: every name stays readable


def tile_basis(counts: list[int], per: float | None = None) -> list[int]:
    """The width each tile asks for in px, by count: together about TILE_ROWS rows of ROW_WIDTH, at least TILE_MIN.
    `tile_rows` turns these into rows of identical tiles. `per`: px per unit of count instead (members of a Gremium:
    one member stays small however few the Gremien are)."""
    total = sum(counts) or 1
    scale = per if per else ROW_WIDTH * TILE_ROWS / total
    return [max(TILE_MIN, round(k * scale)) for k in counts]


ROW_SPLITS = (1, 2, 3, 4)  # tiles per row; each splits evenly on a phone (4 -> 2 lines of 2). Not 6: a sixth of the
# field is narrower than TILE_MIN, so names broke mid-word (test_row_splits_keep_tile_min)
TILE_GAP = 4  # px between the tiles of a row (.trow's gap in cards.css)


def tile_rows(widths: list[int]) -> list[int]:
    """How many tiles each row holds, top to bottom, for tiles sorted largest first with these target widths
    (`tile_basis`): every row is split into equal tiles (ROW_SPLITS) and spans the whole field, so the field is one
    rectangle and the tiles of a row are identical; no row holds fewer tiles than the one above, so a smaller item
    never gets a bigger tile. Chosen to keep each tile closest to its target width (squared log ratio, dynamic
    programming over the sorted list)."""
    import math

    n = len(widths)
    if not n:
        return []
    cost = [[(math.log(ROW_WIDTH / c) - math.log(max(w, 1))) ** 2 for c in ROW_SPLITS] for w in widths]
    inf = float("inf")
    # best[i][j]: least cost of tiles i.. when the row starting at i holds at least ROW_SPLITS[j] tiles per row
    best = [[inf] * len(ROW_SPLITS) for _ in range(n + 1)]
    pick: list[list[int | None]] = [[None] * len(ROW_SPLITS) for _ in range(n + 1)]
    best[n] = [0.0] * len(ROW_SPLITS)
    for i in range(n - 1, -1, -1):
        for j in range(len(ROW_SPLITS) - 1, -1, -1):
            for jj in range(j, len(ROW_SPLITS)):
                c = ROW_SPLITS[jj]
                if i + c > n:
                    break
                v = sum(cost[x][jj] for x in range(i, i + c)) + best[i + c][jj]
                if v < best[i][j]:
                    best[i][j], pick[i][j] = v, jj
    rows, i, j = [], 0, 0
    while i < n:
        jj = pick[i][j]
        if jj is None:  # cannot happen: one tile per row always fits
            raise ValueError("no row plan")
        rows.append(ROW_SPLITS[jj])
        i, j = i + ROW_SPLITS[jj], jj
    return rows


def tiles(items: list[tuple[str, str, int, Counter]], kinds: list[tuple], noun: str, one: str, title: str,
          attrs: list[str] | None = None, listing: bool = False, per: float | None = None) -> str:  # fmt: skip
    """The tile field: one tile per item (href, label, count, counts by kind), largest first, in rows of identical
    tiles that fill the field (`tile_rows`, sized from `tile_basis`), a thin bar inside with the composition by kind
    (`kinds`: (kind, label) in
    the neutral shades, or (kind, label, colour token), e.g. the fractions). A tile is a link to the item's page.
    `attrs`: each tile's values for the controls; `listing`: the tiles are the list a scope filters; `per`: px per
    unit of count (tile_basis)."""
    counts = [k for _, _, k, _ in items]
    out = []
    for i, (href, label, k, c) in enumerate(items):
        total = sum(c.values()) or 1
        bar = "".join(f'<i {_shade(j, kind)} style="width:{_pct(c[kind[0]], total)}%{_bg(kind)}"></i>'
                      for j, kind in enumerate(kinds) if c[kind[0]])  # fmt: skip
        parts = ", ".join(f"{n(c[kk[0]])} {kk[1]}" for kk in kinds if c[kk[0]])
        unit = one if k == 1 else noun
        extra = f" {attrs[i]}" if attrs else ""
        out.append(
            f'<a class="tile" href="{e(href)}"{extra} '
            f'title="{e(label)}: {n(k)} {e(unit)} ({e(parts)})"><span class="tn">{e(label)}</span>'
            f'<span class="tc">{n(k)} <span class="tu">{e(unit)}</span></span><span class="tbar">{bar}</span></a>'
        )
    legend = "".join(f'<span><i {_shade(i, k, "sw")} style="{_bg(k)[1:]}"></i>{e(k[1])}</span>'
                     for i, k in enumerate(kinds))  # fmt: skip
    rows, at = [], 0
    for c in tile_rows(tile_basis(counts, per)):
        rows.append(f'<div class="trow" data-c="{c}">{"".join(out[at : at + c])}</div>')
        at += c
    field = f'<nav class="tiles" aria-label="{e(title)}">{"".join(rows)}</nav>'
    if listing:
        field = (f'<div class="count" data-count></div><div data-rows data-row="a.tile" data-limit="9999">{field}'
                 '<div class="rows"><div class="empty" data-none hidden>Keine Treffer für diese Auswahl.</div></div>'
                 "</div>")  # fmt: skip
    return f'<div class="tiles-wrap"><div class="legend">{legend}</div>{field}</div>'


def month_label(month: str, year: bool = True) -> str:
    """ "2026-03" -> "März 2026" (or "März")."""
    name = MONTHS[int(month[5:7]) - 1]
    return f"{name} {month[:4]}" if year else name


def months_between(first: str, last: str) -> list[str]:
    """Every month from the month of `first` to the month of `last` ("2025-04")."""
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while f"{y}-{m:02d}" <= last[:7]:
        out.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def columns(key: str, months: list[str], counts: dict[str, Counter], groups: list[tuple[str, str, str]],
            title: str, noun: str, one: str, also: str = "") -> str:  # fmt: skip
    """A column per month (value "2026-03"), its height by the month's count, stacked by group (`groups`: (group,
    label, colour token); one group: one colour), the number in its name and tooltip. A column toggles its month;
    `also` chooses a list with it."""
    totals = {m: sum(counts.get(m, Counter()).values()) for m in months}
    most = max([*totals.values(), 1])
    cols = []
    for i, m in enumerate(months):
        c = counts.get(m, Counter())
        k = totals[m]
        parts = ", ".join(f"{label} {n(c[g])}" for g, label, _ in groups if c[g]) if len(groups) > 1 else ""
        name = f"{month_label(m)}: {n(k)} {one if k == 1 else noun}" + (f" ({parts})" if parts else "")
        segs = "".join(f'<i style="flex-grow:{c[g]};background:var(--{colour})"></i>' for g, _, colour in groups
                       if c[g])  # fmt: skip
        quarter = m[5:7] in ("01", "04", "07", "10")  # labelled on a phone too
        first_quarter = quarter and not any(x[5:7] in ("01", "04", "07", "10") for x in months[:i])
        tick = month_label(m, False)[:3] + (f" {m[2:4]}" if i == 0 or m.endswith("-01") or first_quarter else "")
        bar = f'<span class="mc-a"><span class="mc-b" style="height:{_pct(k, most)}%">{segs}</span></span>'
        cls = "mc t" if quarter else "mc"
        cols.append(toggle(key, m, f"{bar}<span class=\"mc-l\">{e(tick)}</span>", cls=cls, label=month_label(m),
                           name=name, also=also))  # fmt: skip
    legend = ("" if len(groups) < 2 else '<div class="legend">' + "".join(
        f'<span><i class="sw" style="background:var(--{colour})"></i>{e(label)}</span>' for _, label, colour in groups)
        + "</div>")  # fmt: skip
    return (f'{legend}<div class="months" role="group" aria-label="{e(title)}" style="--n:{len(months)}">'
            f"{''.join(cols)}</div>")  # fmt: skip


def months_table(months: list[str], counts: dict[str, Counter], groups: list[tuple[str, str, str]], noun: str) -> str:
    """The columns' "Als Tabelle": a row per month, a column per group (or the count)."""
    if len(groups) < 2:
        return table(["Monat", e(noun)], [[month_label(m), n(sum(counts.get(m, Counter()).values()))] for m in months])
    head = ["Monat", *(e(label) for _, label, _ in groups)]
    return table(head, [[month_label(m), *(n(counts.get(m, Counter())[g]) for g, _, _ in groups)] for m in months])


# ---------------------------------------------------------------- the activity strip


def weeks_between(first: str, last: str) -> list[str]:
    """Every ISO week from the week of `first` to the week of `last` (ISO dates)."""
    d = dt.date.fromisoformat(first)
    d -= dt.timedelta(days=d.weekday())
    end = dt.date.fromisoformat(last)
    out = []
    while d <= end:
        out.append(iso_week(d.isoformat()))
        d += dt.timedelta(days=7)
    return out


def week_monday(week: str) -> dt.date:
    y, w = week.split("-W")
    return dt.date.fromisocalendar(int(y), int(w), 1)


def week_label(week: str) -> str:
    y, w = week.split("-W")
    return f"KW {int(w)}/{y}"


def strip_weeks(dates: Iterable[str], sitting_dates: Iterable[str]) -> list[str]:
    """The weeks a strip spans: from the first to the last date of its rows and of the sittings."""
    ds = sorted(d for d in [*dates, *sitting_dates] if d)
    return weeks_between(ds[0], ds[-1]) if ds else []


def strip(weeks: list[str], counts: Counter, sittings: set[str], noun: str, one: str) -> str:
    """The activity strip: a bar per calendar week of the Wahlperiode (dates of Vorgänge fall between sitting weeks
    too), its height by the number of rows in that week, a tick under the sitting weeks. A click on a bar, or a drag
    across several, filters the list to those weeks (`zeit`); the arrow keys move along the bars, Enter or Space
    picks one, Shift with an arrow key widens the range. controls.js redraws the heights for the other filters."""
    if not weeks:
        return ""
    most = max([counts[w] for w in weeks] + [1])
    bars = []
    for i, w in enumerate(weeks):
        k = counts[w]
        s = w in sittings
        name = f"{week_label(w)}{', Sitzungswoche' if s else ''}"
        bars.append(
            f'<button type="button" class="swk{" s" if s else ""}" data-w="{w}" data-label="{e(name)}" '
            f'aria-pressed="false" aria-label="{e(name)}: {n(k)} {e(one if k == 1 else noun)}"'
            f' tabindex="{0 if i == 0 else -1}"><i style="height:{_pct(k, most)}%"></i></button>'
        )
    # (column, date): the first week, then the first week of each quarter, at least 6 weeks apart and 4 from the end
    # (a quarter that has just begun has no room for its label on a phone)
    marks = []
    for i, w in enumerate(weeks):
        m = week_monday(w)
        if i and week_monday(weeks[i - 1]).month != m.month and m.month in (1, 4, 7, 10) and len(weeks) - i >= 4:
            if marks and i - marks[-1][0] < 6:
                marks.pop()
            marks.append((i, m))
        elif not i:
            marks.append((0, m))
    ticks = []
    for j, (i, m) in enumerate(marks):
        end = marks[j + 1][0] if j + 1 < len(marks) else len(weeks)
        label = MONTHS[m.month - 1][:3] + (f" {m.year}" if j == 0 or m.month == 1 else "")
        ticks.append(f'<span style="grid-column:{i + 1}/{end + 1}">{e(label)}</span>')
    return (
        f'<div class="strip" role="group" aria-label="Zeitraum, je Kalenderwoche" data-f="zeit">'
        f'<div class="strip-bars" style="--n:{len(weeks)}">{"".join(bars)}</div>'
        f'<div class="strip-ax" style="--n:{len(weeks)}" aria-hidden="true">{"".join(ticks)}</div>'
        '<div class="strip-out"><span data-range>Ganzer Zeitraum</span> <button type="button" class="zx" '
        'data-zeit-clear hidden>Zeitraum aufheben</button> <span class="faint">Ein Balken je Kalenderwoche, ein '
        "Strich darunter für jede Sitzungswoche.</span></div></div>"
    )


def strip_table(weeks: list[str], counts: Counter, noun: str) -> str:
    """The strip's "Als Tabelle": the rows per month."""
    months: Counter = Counter()
    order: list[tuple[int, int]] = []
    for w in weeks:
        m = week_monday(w)
        if (m.year, m.month) not in order:
            order.append((m.year, m.month))
        months[(m.year, m.month)] += counts[w]
    return table(["Monat", e(noun)], [[f"{MONTHS[mo - 1]} {y}", n(months[(y, mo)])] for y, mo in order])


def activity(dates: list[str], sittings: Iterable[str], noun: str, one: str, title: str = "Zeitraum") -> str:
    """The strip over the rows' dates (ISO dates, one per row), with its table, as a `view`."""
    sitting_dates = list(sittings)
    weeks = strip_weeks(dates, sitting_dates)
    counts = Counter(iso_week(d) for d in dates if d)
    sw = {iso_week(d) for d in sitting_dates}
    if not weeks:
        return ""
    return view("zeit", title, strip(weeks, counts, sw, noun, one), strip_table(weeks, counts, noun))
