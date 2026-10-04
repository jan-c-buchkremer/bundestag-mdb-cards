"""Vote and sitting pages: `abstimmungen/` and `sitzungen/`.

A decision that belongs to exactly one Vorgang lives on that Vorgang's timeline (D15, procedures.py); the others
keep a page here, and the overview lists them all. A sitting page is the zoom level of the time hierarchy below the
week (D18): the agenda with its items as anchors #top-<position> and sub-items #top-<position>-<label>. Facts are
drawn by facts.py. These pages are written as HTML by Python (every link is in the file, so scripts/check_links.py
can follow it); `pages.js` adds the seating charts, the filters and nothing else. German UI, see docs/plan.md."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from research import facts, urls
from research.ui import FOOTER, LANDSCAPE, SITTING_TABS, crumbs, e, long_date, n, shell, short_date, subtabs

TOPICS = 5  # clusters under "Worum ging es"


def week_label(week: str) -> str:
    y, w = week.split("-W")
    return f"Sitzungswoche {int(w)}/{y}"


# ---------------------------------------------------------------- one decision without exactly one Vorgang


def vote_page(d: dict, members: list[list] | None) -> str:
    """The page of a decision that is not a point on one Vorgang's timeline: none, or several Vorgänge."""
    rc = d["kind"] == "namentlich"
    kind = ('<span class="tag">namentliche Abstimmung</span>' if rc
            else '<span class="tag warn">Abstimmung per Handzeichen – nur Fraktionsergebnis</span>')  # fmt: skip
    where = [e(long_date(d["date"]))]
    if d["sitting"]:
        num = d["sitting"].split("/")[1]
        where.append(f'<a href="../{e(urls.sitting(d["sitting"]))}">{e(num)}. Sitzung</a>')
    parts = [
        crumbs(("index.html", "Abstimmungen"), (None, "namentlich" if rc else "per Handzeichen")),
        f'<div class="when">{" · ".join(where)} {kind}</div><h1 class="vh">{e(d["title"])}</h1>',
        facts.decision(d, "../", point=True, detail=True, members=members, when=False),
    ]
    vs = d.get("vorgaenge") or []
    if vs:
        links = "".join(
            f'<li><a href="../{e(urls.vorgang(v))}">{e(d["vorgang_titles"].get(v, v))}</a></li>' for v in vs
        )
        parts.append(f'<h2>Vorgänge</h2><p class="explain">Diese Abstimmung betrifft Drucksachen mehrerer Vorgänge; '
                     f"jeder führt sie in seinem Ablauf.</p><ul>{links}</ul>")  # fmt: skip
    parts.append(f"<footer>{FOOTER}</footer>")
    desc = (f"{'Namentliche Abstimmung' if rc else 'Abstimmung per Handzeichen'} im Bundestag am "
            f"{long_date(d['date'])}: {d['title']} – {d['result'] or 'ohne Ergebnis'}.")  # fmt: skip
    return shell(root="../", kind="p-vote", active="sittings", title=d["title"][:90], desc=desc,
                 head='<script src="../parliament.js"></script>', body="".join(parts),
                 data={"kind": "vote", "id": d["id"]})  # fmt: skip


# ---------------------------------------------------------------- all votes


def compass_link(compass: bool) -> str:
    if not compass:
        return ""
    return (
        " Ausgewählte Abstimmungen als Quiz, um die eigenen Antworten mit den Fraktionen zu vergleichen: "
        '<a href="../kompass.html">Wer stimmt wie ich?</a>'
    )


def votes_index(decisions: list[dict], meta: dict, compass: bool = False) -> str:
    groups: dict[str, list[dict]] = defaultdict(list)
    for d in decisions:
        groups[d["sitting"] or d["date"]].append(d)
    kinds = Counter(d["kind"] for d in decisions)
    results = Counter(d["result"] for d in decisions)
    out = []
    for ds in groups.values():
        first = ds[0]
        if first["sitting"]:
            num = first["sitting"].split("/")[1]
            label = f'<a href="../{e(urls.sitting(first["sitting"]))}">{e(num)}. Sitzung</a>'
        else:
            label = '<span class="faint">Protokoll noch nicht ausgewertet</span>'
        rows = "".join(facts.decision(d, "../", when=False) for d in sorted(ds, key=lambda d: d["order"]))
        out.append(f'<section class="grp"><h3>{label} · {e(long_date(first["date"], True))}</h3>'
                   f'<div class="rows">{rows}</div></section>')  # fmt: skip
    first_date = min((d["date"] for d in decisions), default=meta["sittings"]["from"])
    body = f"""{subtabs("../", SITTING_TABS, "votes")}<h1>Abstimmungen</h1>
<p class="lead">{n(len(decisions))} Beschlüsse seit {e(long_date(first_date))}: {n(kinds["namentlich"])} namentliche Abstimmungen mit der Stimme jedes Mitglieds, {n(kinds["handzeichen"])} Abstimmungen per Handzeichen, bei denen das Protokoll nur festhält, wie die Fraktionen gestimmt haben. {n(results["angenommen"])} angenommen, {n(results["abgelehnt"])} abgelehnt. Überweisungen an Ausschüsse, Wahlen und Fragen der Tagesordnung sind keine Beschlüsse in der Sache und fehlen hier. Wie geschlossen die Fraktionen in den namentlichen Abstimmungen gestimmt haben und wer wann abgewichen ist, zeigt die Seite <a href="geschlossenheit.html">Geschlossenheit der Fraktionen</a>.{compass_link(compass)}</p>
<p class="explain">{facts.relation_note(facts.relation_counts(decisions))}</p>
<div class="filters">
  <input type="search" id="q" placeholder="Titel, Drucksache oder Tagesordnungspunkt …" autocomplete="off">
  <select id="kind"><option value="">namentlich und per Handzeichen</option><option value="namentlich">nur namentlich</option><option value="handzeichen">nur per Handzeichen</option></select>
  <select id="result"><option value="">angenommen und abgelehnt</option><option value="angenommen">angenommen</option><option value="abgelehnt">abgelehnt</option></select>
</div>
<div class="count" id="count"></div>
<div id="groups">{"".join(out)}</div>
<footer>{FOOTER}</footer>"""  # noqa: E501
    return shell(root="../", kind="p-votes", active="sittings", title="Abstimmungen im Bundestag",
                 desc=f"Alle {len(decisions)} Beschlüsse des 21. Deutschen Bundestages, namentlich und per "
                 "Handzeichen, mit Ergebnis und Quelle.", body=body, data={"kind": "votes"})  # fmt: skip


# ---------------------------------------------------------------- sittings


def sitting_page(s: dict, clusters: dict[str, dict] | None = None) -> str:
    week = f"{LANDSCAPE}{s['week']}.html"
    n_speeches = sum(len(i["speeches"]) for i in s["items"])
    n_dec = sum(len(i["decisions"]) for i in s["items"])
    n_rc = sum(1 for i in s["items"] for d in i["decisions"] if d["kind"] == "namentlich")
    time = f" · {e(s['start'])}–{e(s['end'])} Uhr" if s["start"] and s["end"] else ""
    prev = f'<a href="{e(s["prev"])}.html">← {e(s["prev"].split("-")[1])}. Sitzung</a>' if s["prev"] else ""
    nxt = f'<a class="next" href="{e(s["next"])}.html">{e(s["next"].split("-")[1])}. Sitzung →</a>' if s["next"] else ""
    nav = [prev or "<span></span>", nxt]
    summary = [f"{len(s['items'])} Tagesordnungspunkte", f"{n_speeches} Reden"]
    if n_dec:
        summary.append(f"{n_dec} Beschlüsse" + (f", davon {n_rc} namentlich" if n_rc else ""))
    toc = "".join(
        f'<a href="#top-{i["position"]}"><span class="lbl">{e(i["label"])}</span> {e(i["title"])}</a>'
        for i in s["items"]
    )
    head = f"""{crumbs(("index.html", "21. Wahlperiode"), (f"../{urls.week(s['week'])}", week_label(s["week"])), (None, f"{s['number']}. Sitzung"))}
<section class="card sit-head">
  <div class="when">{e(long_date(s["date"], True))}{time}</div>
  <h1>{s["number"]}. Sitzung des 21. Bundestages</h1>
  <div class="lines">{" · ".join(summary)}</div>
  <div class="links"><a href="{e(s["pdf"])}">Plenarprotokoll {e(s["cite"])} (PDF)</a><a href="../{e(urls.week(s["week"]))}">Die Woche im Bundestag</a><a href="{e(week)}">Diese Woche in der Themenlandschaft ↗</a></div>
  <nav class="prevnext">{"".join(nav)}</nav>
</section>
<h2>Tagesordnung</h2>
<nav class="toc">{toc}</nav>"""  # noqa: E501
    items = "".join(agenda_item(i, s, clusters or {}) for i in s["items"])
    body = f"{head}{items}<footer>{FOOTER}</footer>"
    desc = f"{s['number']}. Sitzung des 21. Deutschen Bundestages am {long_date(s['date'])}: Tagesordnung, Reden und Beschlüsse."  # noqa: E501
    title = f"{s['number']}. Sitzung, {short_date(s['date'])}"
    data = {"kind": "sitting", "id": s["id"]}
    head = facts.NOSCRIPT if any(len(i["speeches"]) > facts.SHOWN for i in s["items"]) else ""
    return shell(root="../", kind="p-sitting", active="sittings", title=title, desc=desc, body=body, data=data,
                 head=head)  # fmt: skip


def vorgaenge_line(vs: list[dict]) -> str:
    """The Vorgänge an agenda item's (or sub-item's) Vorlagen belong to, each linked to its page: an item can carry
    Vorlagen of several (docs/plan.md 11.1)."""
    if not vs:
        return ""
    links = " · ".join(f'<a href="../{e(urls.vorgang(v["id"]))}">{e(v["title"])}</a>' for v in vs)
    return f'<div class="drs"><span class="k">Vorgang{"" if len(vs) == 1 else "e"}</span> {links}</div>'


def agenda_item(i: dict, s: dict, clusters: dict[str, dict] | None = None) -> str:
    from research import subtop_pages  # imports this module

    subs = i.get("sub_items")
    parts = [f'<section class="top" id="top-{i["position"]}"><h3><span class="lbl">{e(i["label"])}</span> '
             f'{e(i["title"])}</h3>']  # fmt: skip
    if not subs and (len(i["segments"]) > 1 or (i["segments"] and i["segments"][0] != i["title"])):
        parts.append('<details class="full"><summary>Vollständiger Titel</summary>'
                     + "".join(f"<p>{e(x)}</p>" for x in i["segments"]) + "</details>")  # fmt: skip
    if i["drucksachen"] and not subs:  # a block lists each Vorlage under its sub-TOP
        parts.append(f'<div class="drs"><span class="k">Drucksachen</span> '
                     f"{facts.drucksache_list(i['drucksachen'], '../', limit=8)}</div>")  # fmt: skip
    parts.append(vorgaenge_line(i.get("vorgaenge") or []))
    parts.append(subtop_pages.no_debate_note(i))
    if subs:
        parts.append(subtop_pages.block(i, s))
    decided = i["block_decisions"] if subs else i["decisions"]
    if decided:
        rows = "".join(facts.decision(d, "../", when=False, agenda=False) for d in decided)
        parts.append(f'<div class="decs"><div class="k">Beschlüsse</div>{rows}</div>')
    if i["referred"]:
        drs = i["referred"]["drucksachen"]
        parts.append('<div class="ref"><span class="badge ref">überwiesen</span> '
                     + (f"Drucksache{'n' if len(drs) > 1 else ''} {', '.join(e(x) for x in drs)} an die Ausschüsse"
                        if drs else "an die Ausschüsse") + "</div>")  # fmt: skip
    parts.append(topics_block(i, clusters or {}))
    if i.get("fragestunde"):
        parts.append(f'<p class="explain">{n(i["fragestunde"])} Fragen, Antworten und Nachfragen in der Fragestunde. '
                     "Sie stehen auf den Karten der Beteiligten und zählen nicht als Reden.</p>")  # fmt: skip
    if subs:
        parts.append(subtop_pages.block_speeches(i, s))
    elif i["speeches"]:
        parts.append(facts.speech_block(i["speeches"], str(i["position"])))
    parts.append("</section>")
    return "".join(parts)


def topics(i: dict, clusters: dict[str, dict]) -> list[dict]:
    """The Themenlandschaft clusters of an agenda item's speeches, the most speeches first."""
    count: Counter = Counter()
    label: dict[tuple, str] = {}
    for sp in i["speeches"]:
        c = clusters.get(sp["id"])
        if c:
            key = (c["week"], c["cluster_id"])
            count[key] += 1
            label.setdefault(key, c["label"])
    ranked = sorted(count.items(), key=lambda kv: (-kv[1], label[kv[0]]))
    return [{"week": w, "cluster_id": cid, "label": label[(w, cid)], "n": k} for (w, cid), k in ranked]


def topics_block(i: dict, clusters: dict[str, dict]) -> str:
    """ "Worum ging es": the item's top clusters in the Themenlandschaft; nothing without the landscape's data."""
    found = topics(i, clusters)
    if not found:
        return ""
    total = len(i["speeches"])
    links = "".join(
        f'<a class="topic" href="{LANDSCAPE}{e(t["week"])}.html#cluster={e(t["cluster_id"])}" '
        f'title="{t["n"]} von {total} Reden zu diesem Punkt in diesem Thema der Themenlandschaft">'
        f'{e(t["label"])} <span class="n">{t["n"]}</span></a>'
        for t in found[:TOPICS]
    )
    more = len(found) - TOPICS
    rest = f'<span class="faint">und {more} weitere</span>' if more > 0 else ""
    return (f'<div class="topics"><div class="k">Worum ging es <span class="n">aus der Themenlandschaft'
            "</span></div>"
            f'<div class="chips">{links}{rest}</div></div>')  # fmt: skip


def write_pages(out: Path, decisions: list[dict], members: dict[str, list[list]], sittings: list[dict], meta: dict,
                clusters: dict[str, dict] | None = None, compass: bool = False) -> dict[str, int]:  # fmt: skip
    """Write abstimmungen/ (the pages of decisions without exactly one Vorgang; the others get their stub with the
    Vorgang pages) and sitzungen/; returns the number of pages written per folder."""
    votes_dir, sit_dir = out / "abstimmungen", out / "sitzungen"
    votes_dir.mkdir(parents=True, exist_ok=True)
    sit_dir.mkdir(parents=True, exist_ok=True)
    own = [d for d in decisions if urls.decision(d).startswith("abstimmungen/")]
    for d in own:
        (votes_dir / f"{d['page']}.html").write_text(vote_page(d, members.get(d["id"])), encoding="utf-8")
    (votes_dir / "index.html").write_text(votes_index(decisions, meta, compass), encoding="utf-8")
    for s in sittings:
        (sit_dir / f"{s['page']}.html").write_text(sitting_page(s, clusters), encoding="utf-8")
    from research import weekly  # the calendar; weekly.write rewrites it with the Vorgang pages linked

    (sit_dir / "index.html").write_text(weekly.period_page(sittings, decisions, {}, set()), encoding="utf-8")
    return {"abstimmungen": len(own) + 1, "sitzungen": len(sittings) + 1}
