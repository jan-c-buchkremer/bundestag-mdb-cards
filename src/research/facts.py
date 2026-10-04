"""One rendering component per kind of fact (docs/plan.md section 11, D13): `speech`, `vote`, `decision` and
`drucksache`, with their list forms. Every page that shows one of these facts calls the function here, filtered by
its entity (a person, a group, a place, a procedure, a sitting, a topic): the card, the Fraktion, Gremium and
Bundesregierung pages, the place pages, the Vorgang timeline, the sitting and week pages, the topic pages and the
votes overview. No page renders its own variant.

HTML written by Python, so every link is in the file and scripts/check_links.py can follow it; `root` is the way
back to the site root ("" or "../"). Lists longer than their limit keep every row in the file, the rest hidden
(`data-cut`) until "Alle N zeigen" (pages.js, card.js)."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict

from research import urls
from research.data import NO_FRACTION, VOTE_CHOICES, iso_week, majority
from research.ui import LANDSCAPE, POSITION, SHORT, TOKEN, VOTE, badge, dot, e, frac_link, fraction_order, kind_label, n
from research.ui import short_date as sd

LIMIT = 25  # rows of a list shown before "Alle N zeigen"
SHOWN = 10  # speeches of an agenda item shown before "alle N Reden zeigen"
FACES = 24  # avatars of the hidden speakers under the fade (the row is clipped to the width)
# without JavaScript the long speech lists and cut lists stay open
NOSCRIPT = ("<noscript><style>.sp-list .sp-rest{display:block!important}.sp-list .sp-shown::after,"
            ".sp-bar,.more{display:none!important}[data-cut]{display:grid!important}</style></noscript>")  # fmt: skip


def _link(href: str | None, text: str) -> str:
    return f'<a href="{e(href)}">{text}</a>' if href else text


def _cut(row: str) -> str:
    """A row beyond the list's limit: in the file, hidden until "Alle N zeigen"."""
    return re.sub(r"^<(\w+)", r"<\1 hidden data-cut", row, count=1)


def fact_list(rows: list[str], key: str, empty: str, limit: int | None = LIMIT, note: str = "") -> str:
    """Rows of one kind of fact in a box, the first `limit` shown; `note` goes under the box (where the rest of a
    capped facet lives, D23)."""
    if not rows:
        return f'<div class="rows"><div class="empty">{e(empty)}</div></div>{note}'
    if limit is None or len(rows) <= limit:
        return f'<div class="rows" id="{e(key)}">{"".join(rows)}</div>{note}'
    shown = "".join(rows[:limit]) + "".join(_cut(r) for r in rows[limit:])
    more = f'<button type="button" class="more" data-for="{e(key)}">Alle {n(len(rows))} zeigen</button>'
    return f'<div class="rows" id="{e(key)}">{shown}{more}</div>{note}'


# ---------------------------------------------------------------- speeches

SPEECH_KIND = {"kurz": "kurzer Wortbeitrag", "zwischenfrage": "Zwischenfrage", "kurzintervention": "Kurzintervention"}


def avatar(sp: dict, root: str = "../") -> str:
    """Initials, covered by the portrait when there is one."""
    initials = "".join(w[0] for w in (sp.get("name") or "").split()[-2:] if w)
    photo = (f'<img src="{root}fotos/{e(sp["person"])}.jpg" alt="" loading="lazy" onerror="this.remove()">'
             if sp.get("photo") else "")  # fmt: skip
    return f"{e(initials)}{photo}"


def _speech_what(sp: dict) -> str:
    kind = sp.get("kind") or "rede"
    role = sp.get("role")
    if kind in ("befragung", "fragestunde"):
        where = "Regierungsbefragung" if kind == "befragung" else "Fragestunde"
        return f"{where}: Antwort als {e(role)}" if role else f"{where}: Frage"
    if kind in ("zwischenfrage", "kurzintervention") and sp.get("speaker"):
        return f"{SPEECH_KIND[kind]} an {_link(sp.get('speaker_href'), e(sp.get('speaker_name')))}"
    return SPEECH_KIND.get(kind, "")


def speech(sp: dict, root: str = "../", *, speaker: bool = True, where: bool = True) -> str:
    """One speech (a Rede, a short contribution, a Zwischenfrage, a turn in the Befragung or the Fragestunde): who,
    where (date and agenda item), how long, a short excerpt, and the links to the full text on reden/<id>.html, to
    its place in the Themenlandschaft when it is on the map, and to the protocol PDF. `speaker=False` on the
    speaker's own card, `where=False` under the agenda item it belongs to."""
    kind = sp.get("kind") or "rede"
    person = f"{root}{urls.person(sp['person'])}" if sp.get("person") else None
    if sp.get("speaker"):
        sp = {**sp, "speaker_href": f"{root}{urls.person(sp['speaker'])}"}
    lines = []
    if speaker:
        tag = sp.get("role") or sp.get("fraction") or ""
        lines.append(f'<span class="nm">{_link(person, e(sp.get("name")))}</span>'
                     + (f' <span class="sub">{e(tag)}</span>' if tag else ""))  # fmt: skip
    if where and sp.get("date"):
        at = urls.sitting(sp["sitting"], sp.get("position")) if sp.get("sitting") else None
        title = _link(f"{root}{at}" if at else None, e(sp.get("title") or "Plenarsitzung"))
        lines.append(f'<span class="wh"><span class="d">{sd(sp["date"])}</span> {title}</span>')
    sub = [_speech_what(sp)]
    if not speaker and sp.get("role") and kind not in ("befragung", "fragestunde"):
        sub.append(e(sp["role"]))
    if sp.get("words"):
        sub.append(f"{n(sp['words'])} {'Wort' if sp['words'] == 1 else 'Wörter'}")
    if sp.get("applause"):
        sub.append(f"{n(sp['applause'])}× Beifall")
    inter = sp.get("interruptions") or []
    if inter:
        names = ", ".join(
            _link(f"{root}{urls.person(i['person'])}" if i.get("person") else None, e(i["name"]))
            + (" (Kurzintervention)" if i.get("kind") == "kurzintervention" else "")
            for i in inter
        )
        sub.append(f"{'Zwischenfrage' if len(inter) == 1 else 'Zwischenfragen'} von {names}")
    sub = [x for x in sub if x]
    if sub:
        lines.append(f'<span class="sub">{" · ".join(sub)}</span>')
    if sp.get("excerpt"):
        lines.append(f'<span class="ex">{e(sp["excerpt"])}</span>')
    go = [f'<a href="{root}{e(urls.speech(sp["id"]))}" title="Der ganze Text dieser Rede">Text</a>']
    if sp.get("on_map") and sp.get("date"):
        go.append(f'<a href="{LANDSCAPE}{iso_week(sp["date"])}.html#rede={e(sp["id"])}" '
                  'title="Diese Rede in der Themenlandschaft ihrer Woche">Themenlandschaft ↗</a>')  # fmt: skip
    if sp.get("pdf"):
        go.append(f'<a href="{e(sp["pdf"])}" title="{e(sp.get("cite"))}">Protokoll</a>')
    search = " ".join(str(x) for x in (sp.get("title"), sp.get("date"), sp.get("name"), sp.get("speaker_name")) if x)
    av = (f'<span class="av" style="--c:var(--{TOKEN.get(sp.get("fraction") or "", "reg")})">{avatar(sp, root)}</span>'
          if speaker else "")  # fmt: skip
    return (f'<div class="sp{"" if speaker else " solo"}" data-q="{e(search.lower())}">{av}'
            f'<span class="who">{"".join(lines)}</span><span class="go">{" · ".join(go)}</span></div>')  # fmt: skip


def speech_list(sps: list[dict], root: str = "../", key: str = "sp", *, speaker: bool = True, where: bool = True,
                limit: int | None = LIMIT, empty: str = "Keine Reden.", note: str = "") -> str:  # fmt: skip
    """Speeches as a list in a box (cards, entity facets)."""
    return fact_list([speech(sp, root, speaker=speaker, where=where) for sp in sps], key, empty, limit, note)


def speech_block(sps: list[dict], key: str, root: str = "../") -> str:
    """An agenda item's speeches on the sitting page: beyond SHOWN the list fades out over the faces of the rest and
    a button opens it (pages.js). All rows are in the HTML, so every card link stays in the file."""
    head = f'<div class="k">Reden <span class="n">{len(sps)}</span></div>'
    rows = [speech(sp, root, where=False) for sp in sps]
    if len(sps) <= SHOWN:
        return f'<div class="speeches">{head}{"".join(rows)}</div>'
    people = list({sp["person"]: sp for sp in sps[SHOWN:]}.values())
    faces = "".join(
        f'<span class="av" style="--c:var(--{TOKEN.get(sp["fraction"] or "", "reg")})" title="{e(sp["name"])}">'
        f"{avatar(sp, root)}</span>"
        for sp in people[:FACES]
    )
    rid = f"rest-{key}"
    return (
        f'<div class="speeches sp-list" data-n="{len(sps)}">{head}'
        f'<div class="sp-shown">{"".join(rows[:SHOWN])}</div>'
        f'<div class="sp-rest" id="{rid}">{"".join(rows[SHOWN:])}</div>'
        f'<div class="sp-bar"><span class="sp-faces" aria-hidden="true">{faces}</span>'
        f'<button type="button" class="sp-more" aria-expanded="false" aria-controls="{rid}">alle {len(sps)} Reden '
        "zeigen</button></div></div>"
    )


# ---------------------------------------------------------------- votes


def _counts_line(c: dict) -> str:
    parts = [f"<b>{n(c['yes'])}</b> Ja", f"<b>{n(c['no'])}</b> Nein", f"<b>{n(c['abstain'])}</b> Enthaltung",
             f"<b>{n(c['absent'])}</b> nicht abgegeben"]  # fmt: skip
    if c.get("invalid"):
        parts.append(f"<b>{n(c['invalid'])}</b> ungültig")
    return " · ".join(parts)


def _count_bar(c: dict, cls: str = "bar") -> str:
    """Yes / no / abstain / not cast as one stacked bar."""
    keys = ("yes", "no", "abstain", "absent")
    total = sum(c.get(k, 0) for k in keys) or 1
    tip = ", ".join(f"{VOTE[k]}: {c.get(k, 0)}" for k in keys)
    segs = "".join(f'<i class="v-{k}" style="width:{100 * c.get(k, 0) / total:.2f}%"></i>' for k in keys if c.get(k))
    return f'<span class="{cls}" title="{e(tip)}">{segs}</span>'


def _hands_bar(d: dict, cls: str = "bar") -> str:
    """Show of hands: one segment per fraction, as wide as its seats, coloured by its position."""
    house = d["house"] or {}
    total = sum(house.values()) or 1
    pos = d["fractions"] or {}
    segs, tip = [], []
    for f in sorted(house, key=fraction_order):
        p = pos.get(f)
        segs.append(f'<i class="v-{p or "unknown"}" style="width:{100 * house[f] / total:.2f}%"></i>')
        tip.append(f"{SHORT.get(f, f)}: {POSITION.get(p, 'unbekannt')}")
    title = "Nach Fraktionsstärke, keine Stimmenzahlen. " + ", ".join(tip)
    return f'<span class="{cls}" title="{e(title)}">{"".join(segs)}</span>'


def _positions_line(pos: dict[str, str], root: str) -> str:
    """ "dafür: CDU/CSU, SPD · dagegen: AfD" from the fractions' positions."""
    groups: dict[str, list[str]] = defaultdict(list)
    for f in sorted(pos, key=fraction_order):
        groups[pos[f]].append(frac_link(f, root))
    return " · ".join(f"{POSITION[p]}: <b>{', '.join(groups[p])}</b>" for p in VOTE_CHOICES if groups[p])


def lines(members: list[list]) -> dict[str, str | None]:
    """Each fraction's line on a roll-call vote: data.majority of its rows, none for fraktionslos (D22)."""
    by: dict[str, Counter] = defaultdict(Counter)
    for m in members:
        by[m[2]][m[3]] += 1
    return {f: None if f == NO_FRACTION else majority(t) for f, t in by.items()}


def _table_rc(members: list[list], root: str) -> str:
    by_fraction: dict[str, list[list]] = defaultdict(list)
    for m in members:
        by_fraction[m[2]].append(m)
    line = lines(members)
    rows = []
    for f in sorted(by_fraction, key=fraction_order):
        ms = by_fraction[f]
        t = Counter(m[3] for m in ms)
        dev = [m for m in ms if line[f] and m[3] in VOTE_CHOICES and m[3] != line[f]]
        dev_html = ""
        if dev:
            names = ", ".join(
                _link(f"{root}{urls.person(m[0])}" if m[0] else None, e(m[1])) + f" ({VOTE[m[3]]})"
                for m in sorted(dev, key=lambda m: m[1])
            )
            dev_html = f'<tr class="dev"><td colspan="6">Anders als die Fraktionsmehrheit: {names}</td></tr>'
        rows.append(
            f"<tr><td>{dot(f)} {frac_link(f, root)}</td>"
            + "".join(f'<td class="num">{t[k]}</td>' for k in ("yes", "no", "abstain", "absent"))
            + f"<td>{_count_bar(dict(t), 'bar')}</td></tr>{dev_html}"
        )
    return (
        '<div class="rows"><table class="plenum"><thead><tr><th>Fraktion</th><th>Ja</th>'
        "<th>Nein</th><th>Enth.</th><th>nicht abg.</th><th></th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
        '<p class="explain">„Nicht abgegeben“ sagt nichts über den Grund: Krankheit, Elternzeit, Dienstreisen und '
        "Pairing-Absprachen stehen nicht in den Listen.</p>"
    )


def _table_hands(d: dict, root: str) -> str:
    house = d["house"] or {}
    pos = d["fractions"] or {}
    fractions = sorted(set(house) | set(pos), key=fraction_order)
    if not fractions:
        return ""
    rows = "".join(
        f'<tr><td>{dot(f)} {frac_link(f, root)}</td><td class="num">{house.get(f, "")}</td><td>'
        + (f'<span class="vote {pos[f]}">{POSITION[pos[f]]}</span>' if f in pos
           else '<span class="faint">nicht genannt</span>')
        + "</td></tr>"
        for f in fractions
    )  # fmt: skip
    return (
        '<div class="rows"><table class="plenum"><thead><tr><th>Fraktion</th><th>Sitze</th>'
        f"<th>Position</th></tr></thead><tbody>{rows}</tbody></table></div>"
        '<p class="explain">Die Position ist die, die die Sitzungsleitung für die Fraktion festgestellt hat. '
        "„Nicht genannt“: Die Fraktion kommt im Protokolltext zu dieser Abstimmung nicht vor.</p>"
    )


def _chart(d: dict, members: list[list] | None) -> str:
    """The seating chart of a vote, drawn by pages.js with parliament.js from the data in the element: every
    member's vote with each fraction's line (roll call, D22), or the fractions' positions by seats (show of hands)."""
    if d["kind"] == "namentlich" and members:
        payload = {"mode": "rc", "members": members, "lines": lines(members)}
        extra = ('<label class="toggle"><input type="checkbox" class="dev"> Abweichungen von der Fraktionsmehrheit '
                 "hervorheben</label>"
                 '<p class="note">Sitze nach Fraktionen wie in der Sitzverteilung; in jeder Fraktion nach Stimme, dann '
                 "Name. Ein Schema, nicht die echte Sitzordnung. Punkt antippen oder anklicken öffnet die "
                 "Karte.</p>")  # fmt: skip
    elif d["kind"] != "namentlich" and d.get("fractions") and d.get("house"):
        payload = {"mode": "hands", "house": d["house"], "positions": d["fractions"]}
        extra = ('<p class="note">Abstimmung per Handzeichen: Das Protokoll hält nur fest, wie die Fraktionen gestimmt '
                 "haben, nicht wer. Jede Fraktion ist ganz in der Farbe ihrer Position gezeichnet, so groß wie sie an "
                 "diesem Tag war (nach der Abstimmungsliste der nächsten namentlichen Abstimmung); einzelne "
                 "Abweichungen sieht man nicht.</p>")  # fmt: skip
    else:
        return ""
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", r"<\/")
    return (f'<div class="chart vchart"><div class="pm"></div><div class="legend"></div>{extra}'
            f'<script type="application/json">{data}</script></div>')  # fmt: skip


def own_vote(v: dict) -> str:
    """A member's own roll-call vote and, small and secondary, whether it followed the fraction's line (the line
    and the deviation come from data.votes, i.e. data.majority)."""
    t = v.get("fraction_tally") or {}
    tally = (f"Fraktion {v['fraction']}: {t.get('yes', 0)} Ja, {t.get('no', 0)} Nein, {t.get('abstain', 0)} "
             f"Enthaltung, {t.get('absent', 0)} nicht abgestimmt")  # fmt: skip
    if v["fraction"] == NO_FRACTION:
        mark = '<span class="mark">fraktionslos</span>'
    elif not v.get("line"):
        mark = f'<span class="mark" title="{e(tally)}">Fraktion uneinig</span>'
    elif v.get("deviates"):
        mark = f'<span class="mark dev" title="{e(tally)}">abweichend</span>'
    elif v["vote"] in VOTE_CHOICES:
        mark = f'<span class="mark" title="{e(tally)}">wie Fraktion</span>'
    else:
        mark = f'<span class="mark" title="{e(tally)}">Fraktion: {VOTE[v["line"]]}</span>'
    label = "nicht abgestimmt" if v["vote"] == "absent" else VOTE.get(v["vote"], v["vote"])
    return f'<span class="own"><span class="vote {e(v["vote"])}">{label}</span>{mark}</span>'


def group_position(d: dict, group: str, members: list[list] | None) -> str:
    """A fraction's position on a decision: its line on a roll call (data.majority), else what the chair stated."""
    if d["kind"] == "namentlich":
        pos = lines(members or []).get(group) if members else None
        what = VOTE[pos] if pos else "gespalten" if members else "unbekannt"
    else:
        pos = (d.get("fractions") or {}).get(group)
        what = POSITION[pos] if pos else "nicht genannt"
    return f'<span class="own"><span class="vote {e(pos or "absent")}">{e(what)}</span></span>'


def vote(d: dict, root: str = "../", *, detail: bool = False, members: list[list] | None = None,
         subset: list[list] | None = None) -> str:  # fmt: skip
    """How it was voted on a decision: the house's counts on a roll call, the fractions' positions on a show of
    hands. Compact, a line with a small bar; with `detail`, a big bar, the seating chart and the per-fraction table
    with everyone who voted against their fraction's line. `subset`: only these members' rows are counted, with
    their names (a place's members)."""
    rc = d["kind"] == "namentlich"
    if subset is not None:
        t = Counter(m[3] for m in subset)
        names = "; ".join(
            f"{VOTE[k]}: " + ", ".join(_link(f"{root}{urls.person(m[0])}" if m[0] else None, e(m[1]))
                                       for m in subset if m[3] == k)
            for k in ("yes", "no", "abstain", "absent") if t[k]
        )  # fmt: skip
        return (f'<div class="vt">{_counts_line({k: t[k] for k in ("yes", "no", "abstain", "absent")})}'
                f'<details><summary>Namen</summary>{names}</details></div>')  # fmt: skip
    if rc and d.get("counts"):
        line, bar = _counts_line(d["counts"]), _count_bar(d["counts"], "bar big" if detail else "mini")
    elif rc:
        line, bar = "Keine Stimmenzahlen: zu dieser Abstimmung fehlt die Abstimmungsliste.", ""
    elif d.get("fractions"):
        line = _positions_line(d["fractions"], root)
        bar = _hands_bar(d, "bar big" if detail else "mini") if d.get("house") else ""
    else:
        line, bar = "Das Protokoll nennt bei dieser Abstimmung per Handzeichen keine Fraktionen, nur das Ergebnis.", ""
    if not detail:
        return f'<div class="vt">{line} {bar}</div>'
    table = _table_rc(members, root) if rc and members else _table_hands(d, root) if not rc else ""
    if rc and not members:
        table = ('<p class="explain">Zu dieser Abstimmung gibt es keine Abstimmungsliste mit Einzelstimmen (im '
                 "Protokoll verlesen, aber nicht in den Listen des Bundestages).</p>")  # fmt: skip
    return f'<div class="vt big">{line}{bar}</div>{_chart(d, members)}' + (
        f'<details class="vtab"><summary>Nach Fraktionen</summary>{table}</details>' if table else ""
    )


# ---------------------------------------------------------------- decisions


def _sources(d: dict, root: str) -> str:
    items = []
    s = d.get("sources") or {}
    if s.get("xlsx"):
        items.append(f'<li>Abstimmungsliste {e(s.get("cite"))}: <a href="{e(s["xlsx"])}">XLSX</a>'
                     + (f', <a href="{e(s["pdf"])}">PDF</a>' if s.get("pdf") else "")
                     + ". © Deutscher Bundestag</li>")  # fmt: skip
    if d.get("protocol"):
        items.append(f'<li>Plenarprotokoll {e(d["cite"])}: <a href="{e(d["protocol"])}">PDF</a>. '
                     "© Deutscher Bundestag</li>")  # fmt: skip
    for r in d.get("drucksachen") or []:
        items.append(f"<li>Drucksache {drucksache(r, root, compact=True)}"
                     + (f" ({e(r['type'])})" if r.get("type") else "")
                     + f': <a href="{e(r["pdf"])}">PDF</a></li>')  # fmt: skip
    return f'<ul class="sources">{"".join(items)}</ul>' if items else ""


def decision(d: dict, root: str = "../", *, point: bool = False, detail: bool = False,
             members: list[list] | None = None, own: dict | None = None, group: str | None = None,
             subset: list[list] | None = None, when: bool = True, agenda: bool = True) -> str:  # fmt: skip
    """One decision of the Bundestag: result, what it was about, the agenda item and Drucksachen, and how it was
    voted (`vote`). Linked to its canonical place (D15) unless it is rendered there (`point`, with the anchor
    #abst-<page id>). `own`: a member's vote (card); `group`: a fraction's position; `subset`: a place's members;
    `detail`: seating chart, per-fraction table, the chair's words and the sources."""
    title = e(d["title"])
    head = title if point else f'<a class="ti" href="{root}{e(urls.decision(d))}">{title}</a>'
    sub = []
    if when and d.get("date"):
        sub.append(sd(d["date"]))
    if d.get("subject") and d["subject"] != d["title"]:
        sub.append(e(d["subject"]))
    if agenda and d.get("agenda") and d.get("sitting"):
        a = d["agenda"]
        label = a["label"] + (f" › {d['sub']['label']}" if isinstance(d.get("sub"), dict) else "")
        sub_label = d["sub"]["label"] if isinstance(d.get("sub"), dict) else None
        num = d["sitting"].split("/")[1]
        sub.append(f'<a href="{root}{e(urls.sitting(d["sitting"], a["position"], sub_label))}">{e(num)}. Sitzung, '
                   f"{e(label)}</a>")  # fmt: skip
    if d.get("drucksachen"):
        sub.append("Drs. " + drucksache_list(d["drucksachen"], root, limit=4))
    if len(d.get("vorgaenge") or []) > 1:
        sub.append(f"betrifft {n(len(d['vorgaenge']))} Vorgänge")
    right = f'<span class="k">{kind_label(d["kind"])}</span>'
    if own:
        right = own_vote(own) + right
    elif group:
        right = group_position(d, group, members) + right
    anchor = f' id="abst-{e(d["page"])}"' if point else ""
    attrs = (f' data-kind="{e(d["kind"])}" data-result="{e(d.get("result") or "")}"'
             + (' data-dev="1"' if own and own.get("deviates") else ""))  # fmt: skip
    body = vote(d, root, detail=detail, members=members, subset=subset)
    if detail and d.get("text"):
        paras = "".join(f"<p>{e(p)}</p>" for p in d["text"].split("\n\n") if p.strip())
        body += (
            f'<details class="vtab"><summary>Aus dem Protokoll</summary><blockquote class="chair">{paras}'
            "</blockquote></details>"
        )
    if detail:
        body += _sources(d, root)
    note = ""
    if d.get("result_from") in ("counts", "count"):
        note = ('<div class="sub">Ergebnis aus den Stimmenzahlen der Abstimmungsliste; das Protokoll dieser '
                "Abstimmung ist noch nicht ausgewertet.</div>")  # fmt: skip
    if (d.get("agenda") or {}).get("no_debate") or (isinstance(d.get("sub"), dict) and d["sub"].get("no_debate")):
        note += '<div class="sub">Laut Protokoll ohne Aussprache abgestimmt.</div>'
    return (f'<div class="dec{" hi" if own and own.get("deviates") else ""}"{anchor}{attrs}>'
            f'<div class="dh">{badge(d.get("result"))}<span class="dt">{head}</span>'
            f'<span class="dr">{right}</span></div>'
            f'<div class="sub">{" · ".join(sub)}</div>{note}{body}</div>')  # fmt: skip


def decision_list(ds: list[dict], root: str = "../", key: str = "dec", *, limit: int | None = LIMIT,
                  empty: str = "Keine Beschlüsse.", note: str = "", own_by_id: dict[str, dict] | None = None,
                  **kw) -> str:  # fmt: skip
    """Decisions as a list in a box; keyword arguments go to `decision` (members, group and subset may be
    callables taking the decision); `own_by_id` gives a member's own vote per decision id (the card)."""
    rows = []
    for d in ds:
        args = {k: (v(d) if callable(v) else v) for k, v in kw.items()}
        if own_by_id is not None:
            args["own"] = own_by_id.get(d["id"])
        rows.append(decision(d, root, **args))
    return fact_list(rows, key, empty, limit, note)


def relation_counts(decisions: list[dict]) -> dict[str, int]:
    """How decisions and Vorgänge relate in the store: decisions in all, those of exactly one Vorgang (a point on its
    timeline, D15), and the Vorgänge with two or more decisions."""
    per: Counter = Counter(v for d in decisions if len(d.get("vorgaenge") or []) == 1 for v in d["vorgaenge"])
    return {"decisions": len(decisions), "on_one": sum(per.values()), "several": sum(1 for k in per.values() if k > 1)}


def relation_note(c: dict[str, int], root: str = "../") -> str:
    """One short paragraph on votes and Vorgänge, for the Abstimmungen tab and every Vorgang page (plan 12.4)."""
    return (
        f'Ein <a href="{root}vorgaenge/index.html">Vorgang</a> hat oft mehrere Abstimmungen: über '
        "Änderungs- und Entschließungsanträge, die zweite Beratung in Teilen, zuletzt die Schlussabstimmung "
        f"({n(c['several'])} {'Vorgang hat' if c['several'] == 1 else 'Vorgänge haben'} zwei oder mehr). "
        "Eine Abstimmung, die zu genau einem Vorgang gehört, ist "
        f"ein Punkt in seinem Ablauf ({n(c['on_one'])} von {n(c['decisions'])}); die übrigen gehören zu keinem oder zu "
        "mehreren Vorgängen und haben eine eigene Seite, die jeden betroffenen Vorgang nennt. Jede Abstimmung steht "
        "außerdem bei der Sitzung, in der sie stattfand."
    )


# ---------------------------------------------------------------- Drucksachen


def drucksache(r: dict, root: str = "../", *, compact: bool = False, own: bool = False) -> str:
    """One Drucksache. Compact: its number, linked to DIP (else the PDF), inline in a sentence or a list. Else a row
    with date, title, type, number, Urheber count and subjects, and the links DIP, PDF and, when it belongs to one
    Vorgang with a page, that Vorgang. `own`: shown on an author's card (the activity instead of the type)."""
    number = (
        f'<a href="{e(r.get("url") or r.get("pdf"))}" title="{e(r.get("type") or "Drucksache")}">{e(r["number"])}</a>'
    )
    if compact:
        return number
    activity = r.get("activity")
    sub = [e("Schriftliche Frage" if activity == "Frage" else activity or r.get("type") or "Drucksache"),
           f"Drs. {number}"]  # fmt: skip
    authors = r.get("authors")
    if own and activity != "Frage" and authors:
        sub.append("allein gezeichnet" if authors == 1 else f"eine von {n(authors)} Namen")
    elif r.get("originators"):
        sub.append(e(", ".join(r["originators"][:3]) + (" …" if len(r["originators"]) > 3 else "")))
    if r.get("subjects"):
        sub.append(e(", ".join(r["subjects"])))
    go = []
    if r.get("vorgang"):
        go.append(f'<a href="{root}{e(urls.vorgang(r["vorgang"]))}" title="Der Vorgang dieser Drucksache">Vorgang</a>')
    if r.get("pdf"):
        go.append(f'<a href="{e(r["pdf"])}" title="{e(r.get("cite") or r["number"])}">PDF</a>')
    small = ' data-small="1"' if authors and authors <= 10 else ""
    return (f'<div class="row drs"{small}><div class="d">{sd(r["date"]) if r.get("date") else ""}</div>'
            f'<div class="t">{e(r.get("title") or r.get("type") or r["number"])}'
            f'<div class="sub">{" · ".join(sub)}</div>'
            f'</div><div class="l">{"".join(go)}</div></div>')  # fmt: skip


def drucksache_list(refs: list[dict], root: str = "../", key: str = "drs", *, compact: bool = True,
                    limit: int | None = None, empty: str = "Keine Drucksachen.", note: str = "",
                    own: bool = False) -> str:  # fmt: skip
    """Drucksachen: compact, their numbers inline ("21/1, 21/2 und 3 weitere"); else rows in a box."""
    if not compact:
        return fact_list([drucksache(r, root, own=own) for r in refs], key, empty, limit or LIMIT, note)
    shown = refs if limit is None else refs[:limit]
    more = len(refs) - len(shown)
    return (", ".join(drucksache(r, root, compact=True) for r in shown)
            + (f' <span class="faint">und {more} weitere</span>' if more > 0 else ""))  # fmt: skip
