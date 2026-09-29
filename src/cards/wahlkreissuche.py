"""Meinen Wahlkreis finden: `wahlkreise/suche.html`, a client-side Gemeinde search built from the foundation's
`constituency_municipality` (skipped when that table does not exist yet, e.g. an older store).

Per Gemeinde: its Wahlkreis, or several for the 18 Gemeinden the Bundeswahlleiterin's file splits across
Wahlkreise (the file names only a running Gemeindeteil number, not which streets belong where — a finer lookup
needs another source, see docs/decisions.md). Per Wahlkreis: the directly elected member, the list members who
stood there as candidates (`election_candidacy.constituency_number`), and the other list members of the Land,
collapsed. No postcodes this round: they cannot be mapped to a Gemeinde without a further source (OpenPLZ)."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from pathlib import Path

from cards.data import ELECTION, has_table
from cards.pages import FOOTER, shell

STYLE = """<style>
.wks { max-width: 620px; }
.wks .field { position: relative; margin: 0 0 6px; }
.wks input[type=search] { width: 100%; box-sizing: border-box; background: var(--card); color: var(--text);
  border: 1px solid var(--line); border-radius: 8px; padding: 9px 12px; font-size: 14px; }
.wks .suggest { position: absolute; z-index: 2; top: calc(100% + 4px); left: 0; right: 0; background: var(--card);
  border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 6px 20px rgba(0,0,0,.08); max-height: 320px;
  overflow-y: auto; }
.wks .suggest button { display: block; width: 100%; box-sizing: border-box; text-align: left; background: none;
  border: none; border-top: 1px solid var(--line); padding: 8px 12px; font: inherit; color: var(--text); cursor: pointer; }
.wks .suggest button:first-child { border-top: none; }
.wks .suggest button:hover, .wks .suggest button.hi { background: var(--bg); }
.wks .suggest .d { color: var(--muted); font-size: 12.5px; }
.wks .gm { margin: 18px 0 4px; font-size: 15px; }
.wks .wkblock { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px;
  margin: 12px 0; }
.wks .wkblock h2 { font-size: 15px; margin: 0 0 10px; }
.wks .row2 { margin: 6px 0; font-size: 13.5px; }
.wks .row2 .k { display: inline-block; min-width: 200px; font-size: 11px; font-weight: 600; letter-spacing: .05em;
  text-transform: uppercase; color: var(--faint); vertical-align: top; }
.wks .row2 a { display: inline-flex; align-items: center; gap: 6px; margin: 0 12px 4px 0; }
.wks .wkblock .dot { width: 8px; height: 8px; }
.wks details.open { margin-top: 8px; font-size: 13.5px; }
.wks details.open summary { cursor: pointer; color: var(--muted); }
.wks details.open .list { margin-top: 8px; }
</style>"""  # noqa: E501

# kept in sync with the STATES/FRACTION_COLORS maps in index.html
JS = """<script>
(function () {
  const STATES = { BW: 'Baden-Württemberg', BY: 'Bayern', BE: 'Berlin', BB: 'Brandenburg', HB: 'Bremen', HH: 'Hamburg',
    HE: 'Hessen', MV: 'Mecklenburg-Vorpommern', NI: 'Niedersachsen', NW: 'Nordrhein-Westfalen', RP: 'Rheinland-Pfalz',
    SL: 'Saarland', SN: 'Sachsen', ST: 'Sachsen-Anhalt', SH: 'Schleswig-Holstein', TH: 'Thüringen' };
  const FRACTION_COLORS = { 'CDU/CSU': '--cdu', 'SPD': '--spd', 'AfD': '--afd', 'BÜNDNIS 90/DIE GRÜNEN': '--gru',
    'Die Linke': '--lin', 'fraktionslos': '--frl' };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const $ = id => document.getElementById(id);
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const color = f => FRACTION_COLORS[f] ? css(FRACTION_COLORS[f]) : css('--reg');
  const norm = s => String(s ?? '').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
  const q = $('gq'), suggest = $('suggest'), hint = $('hint'), result = $('result');
  const HAY = PAGE.gemeinden.map((g, i) => { g._i = i; return norm(`${g.n} ${g.d}`); });
  let items = [], hi = -1;

  function memberLink(m) {
    return `<a href="../${esc(m.id)}.html"><span class="dot" style="background:${color(m.fraction)}"></span>${esc(m.name)}${m.left ? ' <span class="faint">(ausgeschieden)</span>' : ''}</a>`;
  }

  function wkBlock(nr) {
    const meta = PAGE.wk[nr] || {};
    const d = PAGE.direct[nr];
    const cs = PAGE.candidates[nr] || [];
    const stateName = STATES[meta.state] || meta.state || '';
    const others = (PAGE.list_by_state[meta.state] || []).filter(m => !cs.some(c => c.id === m.id));
    return `<div class="wkblock"><h2>Wahlkreis ${esc(nr)} · ${esc(meta.name || '')} <span class="faint">· ${esc(stateName)}</span></h2>
      <div class="row2"><span class="k">direkt gewählt</span>${d ? memberLink(d) : '<span class="faint">kein direkt gewähltes Mitglied</span>'}</div>
      ${cs.length ? `<div class="row2"><span class="k">Landesliste, hier kandidiert</span>${cs.map(memberLink).join('')}</div>` : ''}
      ${others.length ? `<details class="open"><summary>${others.length} weitere Landeslisten-Abgeordnete aus ${esc(stateName)}</summary><div class="list">${others.map(memberLink).join('')}</div></details>` : ''}
      </div>`;
  }

  function renderResult(g) {
    const split = g.w.length > 1
      ? '<p class="explain">Diese Gemeinde ist auf mehrere Wahlkreise aufgeteilt (nach Ortsteil); welcher Teil zu welchem Wahlkreis gehört, steht hier nicht – alle betroffenen Wahlkreise:</p>' : '';
    result.innerHTML = `<div class="gm"><b>${esc(g.n)}</b> <span class="faint">· ${esc(g.d)} · ${esc(STATES[g.s] || g.s)}</span></div>${split}${g.w.map(wkBlock).join('')}`;
    hint.hidden = true;
  }

  function closeSuggest() { suggest.hidden = true; items = []; hi = -1; }

  function renderSuggest(list) {
    items = list;
    hi = -1;
    if (!list.length) { closeSuggest(); return; }
    suggest.innerHTML = list.map((g, i) => `<button type="button" data-i="${i}">${esc(g.n)} <span class="d">${esc(g.d)} · ${esc(STATES[g.s] || g.s)}</span></button>`).join('');
    suggest.hidden = false;
  }

  function pick(g) {
    q.value = g.d && g.d !== g.n ? `${g.n} (${g.d})` : g.n;
    closeSuggest();
    renderResult(g);
  }

  q.addEventListener('input', () => {
    const query = norm(q.value.trim());
    result.innerHTML = '';
    if (query.length < 2) { closeSuggest(); hint.hidden = false; hint.textContent = 'Mindestens zwei Zeichen eingeben.'; return; }
    hint.hidden = true;
    const words = query.split(/\\s+/).filter(Boolean);
    const matched = PAGE.gemeinden.filter(g => words.every(w => HAY[g._i].includes(w)));
    matched.sort((a, b) => HAY[a._i].indexOf(query) - HAY[b._i].indexOf(query) || a.n.localeCompare(b.n, 'de'));
    if (!matched.length) { closeSuggest(); hint.hidden = false; hint.textContent = 'Keine Gemeinde gefunden.'; return; }
    renderSuggest(matched.slice(0, 12));
  });

  suggest.addEventListener('click', e => {
    const btn = e.target.closest('button[data-i]');
    if (btn) pick(items[+btn.dataset.i]);
  });

  q.addEventListener('keydown', e => {
    if (suggest.hidden) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      hi = Math.max(0, Math.min(items.length - 1, hi + (e.key === 'ArrowDown' ? 1 : -1)));
      suggest.querySelectorAll('button').forEach((b, i) => b.classList.toggle('hi', i === hi));
      suggest.children[hi]?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      pick(items[hi >= 0 ? hi : 0]);
    } else if (e.key === 'Escape') {
      closeSuggest();
    }
  });

  document.addEventListener('click', e => { if (!e.target.closest('.wks .field')) closeSuggest(); });
})();
</script>"""  # noqa: E501


def municipalities(conn: sqlite3.Connection) -> list[dict] | None:
    """Compact Gemeinde -> Wahlkreis(e) index, one entry per (name, Kreis, Land); a split Gemeinde carries
    several Wahlkreis numbers. None when the foundation has not filled `constituency_municipality` yet."""
    if not has_table(conn, "constituency_municipality"):
        return None
    grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for r in conn.execute(
        "SELECT name, district, state, constituency_number FROM constituency_municipality "
        "WHERE election = ? ORDER BY name COLLATE NOCASE",
        (ELECTION,),
    ):
        grouped[(r["name"], r["district"], r["state"])].append(r["constituency_number"])
    return [
        {"n": name, "d": district, "s": state, "w": sorted(set(numbers))}
        for (name, district, state), numbers in grouped.items()
    ]


def member_index(cards: list[dict]) -> dict:
    """Per Wahlkreis: the directly elected member and the list members who stood there; per Land: every current
    list member. Built from each card's `election` (btw25 `election_candidacy`), not the Stammdaten mandate, so
    a former mandate's Wahlkreis never leaks in."""
    direct: dict[str, dict] = {}
    candidates: dict[str, list[dict]] = defaultdict(list)
    by_state: dict[str, list[dict]] = defaultdict(list)
    for c in cards:
        el = c.get("election")
        if not el:
            continue
        left = bool((c.get("mandate") or {}).get("to"))
        ref = {"id": c["id"], "name": c["name"], "fraction": c["fraction"], "left": left}
        if el["via"] == "constituency" and el["number"] is not None:
            direct[str(el["number"])] = ref
        elif el["via"] == "list":
            if el["list_state"]:
                by_state[el["list_state"]].append({**ref, "number": el["number"]})
            if el["number"] is not None:
                candidates[str(el["number"])].append(ref)
    return {"direct": direct, "candidates": candidates, "list_by_state": by_state}


def page(gemeinden: list[dict], members: dict, wks: list[dict]) -> str:
    wk_meta = {str(w["number"]): {"name": w["name"], "state": w["state"]} for w in wks}
    data = {"kind": "wahlkreissuche", "gemeinden": gemeinden, "wk": wk_meta, **members}
    body = (
        '<section class="card"><h1>Meinen Wahlkreis finden</h1><div class="lines">'
        "Gemeinde oder Stadt eingeben: der Wahlkreis der Bundestagswahl 2025, wer ihn direkt gewonnen hat, wer dort "
        "über die Landesliste kandidiert hat, und die übrigen Landeslisten-Abgeordneten des Landes. "
        '<a href="../daten.html">Über die Daten</a></div></section>'
        '<div class="wks">'
        '<div class="field"><input type="search" id="gq" placeholder="Gemeinde oder Stadt …" autocomplete="off" '
        'aria-label="Gemeinde oder Stadt"><div id="suggest" class="suggest" hidden></div></div>'
        '<p class="explain" id="hint">Mindestens zwei Zeichen eingeben.</p>'
        '<div id="result"></div>'
        "</div>"
        f"<footer>{FOOTER}</footer>{JS}"
    )
    return shell(
        root="../", kind="p-wksuche", active="cards", title="Meinen Wahlkreis finden – Bundestag, 21. Wahlperiode",
        desc="Gemeinde eingeben und den Bundestagswahlkreis 2025 finden: direkt gewähltes Mitglied, "
             "Landeslisten-Kandidaturen und die übrigen Landeslisten-Abgeordneten des Landes.",
        body=body, data=data, head=STYLE,
    )  # fmt: skip


def write(conn: sqlite3.Connection, out: Path, cards: list[dict], wks: list[dict]) -> dict[str, int]:
    """Write wahlkreise/suche.html; returns {} when the foundation has no `constituency_municipality` yet."""
    gemeinden = municipalities(conn)
    if gemeinden is None:
        return {}
    d = out / "wahlkreise"
    d.mkdir(parents=True, exist_ok=True)
    (d / "suche.html").write_text(page(gemeinden, member_index(cards), wks), encoding="utf-8")
    return {"wahlkreise": 1}
