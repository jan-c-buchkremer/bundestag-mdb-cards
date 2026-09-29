"""Wer stimmt wie ich? `kompass.html`, a static, fully client-side vote-matching quiz built from a curated
selection of decisions (`compass_candidates.json`). Nothing about the quiz runs on a server: the page ships every
question, every fraction's position and, for roll-call questions, every member's vote as inlined JSON; the browser
asks and scores every question itself (the inline SCRIPT), and answers are never written to storage or sent anywhere.

The candidate file holds about 40 draft decisions Jan reviews by hand: `selected` picks roughly 20 for the quiz,
`question_approved` confirms the neutral wording. The page is written only once at least ten candidates have both
flags set, so an unfinished selection publishes nothing. `why` and `review` are notes for the curator and never reach
the page; `note` and `camp_vote_risk` (a vote that may follow the coalition/opposition line more than the topic) are
shown next to the fractions' positions in the results. `invert` marks a candidate whose question is phrased as
the proposal itself while the roll call actually voted on a committee recommendation to *reject* it (a "Ja" in the
store then means "Nein" to the question); `yes_on_decision` documents in plain German what a "Ja" in the store did,
so the flip can be checked against the chair's protocol text.

Matching against fractions uses every selected decision, roll-call or show of hands (`decision_fraction` for the
latter, the line each fraction voted most often for the former, as the vote pages and cards already do). Matching
against an individual member or a Wahlkreis's members uses roll-call questions only, since only they carry a named
vote per member."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from cards.data import VOTE_CHOICES, majority
from cards.pages import FOOTER, ORDER, SHORT, TOKEN, fraction_order, shell

HERE = Path(__file__).parent
CANDIDATES_PATH = HERE / "compass_candidates.json"
MIN_QUESTIONS = 10  # nothing is written below this


def candidates() -> list[dict]:
    return json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))


def _flip(pos: str | None, invert: bool) -> str | None:
    if not invert or pos is None:
        return pos
    return {"yes": "no", "no": "yes", "abstain": "abstain"}[pos]


def fraction_position(decision: dict, fraction: str) -> str | None:
    """The fraction's yes/no/abstain on one decision: the line it voted most often on a roll call (as the vote
    pages, cards and `cohesion.py` read it), or its recorded position on a show-of-hands decision. None when the
    fraction did not vote or has no line (a tie)."""
    if decision["kind"] == "namentlich":
        tally = (decision.get("fractions") or {}).get(fraction)
        if not tally or not any(tally.get(c) for c in VOTE_CHOICES):
            return None
        return majority(Counter({c: tally.get(c, 0) for c in VOTE_CHOICES}))
    return (decision.get("fractions") or {}).get(fraction)


def fraction_positions(decision: dict, invert: bool) -> dict[str, str]:
    fractions = list((decision.get("fractions") or {}).keys())
    out = {}
    for f in sorted(fractions, key=fraction_order):
        pos = _flip(fraction_position(decision, f), invert)
        if pos:
            out[f] = pos
    return out


def roll_call_votes(decision_id: str, invert: bool, members: dict[str, list[list]]) -> list[list]:
    """[person id, yes/no/abstain] for every member with a linked person id who cast yes, no or abstain on this
    roll call, name and fraction left out (the page's member index already carries them). Absent and invalid votes
    are left out, same as a skipped question: there is nothing to compare."""
    out = []
    for pid, _name, _fraction, vote in members.get(decision_id, []):
        if pid is None or vote not in VOTE_CHOICES:
            continue
        out.append([pid, _flip(vote, invert)])
    return out


def build_questions(cands: list[dict], decisions: list[dict], members: dict[str, list[list]]) -> list[dict]:
    by_id = {d["id"]: d for d in decisions}
    out = []
    for c in cands:
        if not (c["selected"] and c["question_approved"]):
            continue
        d = by_id.get(c["id"])
        if d is None or d["kind"] != c["kind"]:
            continue  # a candidate the store no longer has, or whose kind changed since curation
        out.append(
            {
                "id": d["id"], "page": d["page"], "date": d["date"], "title": d["title"], "kind": d["kind"],
                "drucksachen": d["drucksachen"],
                "topic": c["topic"], "question": c["question"], "note": c.get("note"),
                "caution": c.get("camp_vote_risk"), "initiator": c["initiator"],
                "fractions": fraction_positions(d, c["invert"]),
                "votes": roll_call_votes(d["id"], c["invert"], members) if d["kind"] == "namentlich" else [],
            }
        )  # fmt: skip
    return out


def member_index(cards: list[dict]) -> list[dict]:
    """Name, fraction and Wahlkreis of every member card, for the lookup step; speaker cards have no vote."""
    out = []
    for c in cards:
        if c["kind"] != "member":
            continue
        m = c["mandate"] or {}
        out.append({"id": c["id"], "name": c["name"], "fraction": c["fraction"],
                    "wk": m.get("number"), "wk_name": m.get("constituency")})  # fmt: skip
    return out


STYLE = """<style>
.cps h1 { font-size: 26px; font-weight: 600; letter-spacing: -.02em; margin: 8px 0 6px; }
.cps h2 { font-size: 16px; font-weight: 600; margin: 24px 0 8px; }
.cps .lead { font-size: 15px; }
.cps .disclaimer { background: var(--bg); border: 1px solid var(--line); border-radius: 10px; padding: 10px 14px; font-size: 13.5px; color: var(--muted); margin: 14px 0; }
.cps details.method { margin: 12px 0; font-size: 13.5px; }
.cps details.method summary { cursor: pointer; font-weight: 600; color: var(--muted); }
.cps details.method dl { margin: 8px 0 0; }
.cps details.method dt { font-weight: 600; margin-top: 8px; }
.cps details.method dd { margin: 2px 0 0; }
.cps #start { margin: 16px 0; }
.cps button.primary { font: inherit; font-weight: 600; padding: 10px 20px; border-radius: 10px; border: 0; background: var(--accent); color: #fff; cursor: pointer; }
.cps button.primary:hover { filter: brightness(1.08); }
.cps #quiz, .cps #results { display: none; }
.cps.q-active #intro { display: none; } .cps.q-active #quiz { display: block; }
.cps.r-active #intro, .cps.r-active #quiz { display: none; } .cps.r-active #results { display: block; }
.cps .progress { font-size: 13px; color: var(--muted); margin-bottom: 4px; }
.cps .qcard { border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; }
.cps .qcard .topic { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }
.cps .qcard .qtext { font-size: 19px; font-weight: 600; margin: 6px 0 14px; }
.cps .important { display: flex; align-items: center; gap: 6px; font-size: 13.5px; color: var(--muted); margin-bottom: 14px; }
.cps .answers { display: flex; flex-wrap: wrap; gap: 8px; }
.cps .answers button { font: inherit; font-size: 14.5px; padding: 9px 16px; border-radius: 9px; border: 1px solid var(--line); background: var(--card); cursor: pointer; }
.cps .answers button:hover { border-color: var(--accent); }
.cps .answers button.skip { margin-left: auto; color: var(--muted); border-style: dashed; }
.cps .nav { margin-top: 14px; font-size: 13px; }
.cps .nav button { font: inherit; background: none; border: 0; color: var(--muted); cursor: pointer; padding: 0; }
.cps .bars .row { display: grid; grid-template-columns: 150px 1fr 48px; align-items: center; gap: 10px; margin: 6px 0; font-size: 14px; }
.cps .bars .bar { height: 14px; border-radius: 7px; background: var(--bg); overflow: hidden; }
.cps .bars .bar span { display: block; height: 100%; }
.cps .bars .pct { text-align: right; font-variant-numeric: tabular-nums; }
.cps table.breakdown { width: 100%; border-collapse: collapse; font-size: 13.5px; margin-top: 8px; }
.cps table.breakdown th { text-align: left; font-weight: 500; color: var(--muted); font-size: 12px; padding: 6px 8px; border-bottom: 1px solid var(--line); }
.cps table.breakdown td { padding: 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
.cps table.breakdown .note { color: var(--muted); font-size: 12.5px; margin-top: 4px; }
.cps table.breakdown .caution { color: var(--text); }
.cps table.breakdown .src { font-size: 12.5px; margin-top: 4px; }
.cps .lookup { border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px; margin-top: 10px; }
.cps .lookup input { font: inherit; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line); width: 100%; max-width: 320px; }
.cps .lookup .list { margin-top: 8px; max-height: 220px; overflow: auto; }
.cps .lookup .list button { display: block; width: 100%; text-align: left; font: inherit; padding: 6px 8px; border: 0; background: none; cursor: pointer; border-radius: 6px; }
.cps .lookup .list button:hover { background: var(--bg); }
.cps .lookup .result { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); }
.cps .restart { margin-top: 20px; }
</style>"""  # noqa: E501

SCRIPT = """<script>
(() => {
  const Q = PAGE.questions, MEMBERS = PAGE.members;
  const SHORT = PAGE.short, TOKEN = PAGE.token, ORDER = PAGE.order;
  const root = document.querySelector('.cps');
  const answers = new Map();  // id -> {answer: 'yes'|'no'|'abstain', important: bool}
  let i = 0;

  function fracOrder(f) { const k = ORDER.indexOf(f); return k === -1 ? ORDER.length : k; }
  function fracLabel(f) { return SHORT[f] || f; }
  function fracColor(f) { return 'var(--' + (TOKEN[f] || 'reg') + ')'; }

  // Wahl-O-Mat-style points for one answer against one position: same position 2, one side neutral (Enthaltung)
  // 1, opposite (Ja vs. Nein) 0. A doubled ("wichtig") question doubles both the points and the achievable total.
  function points(a, b) {
    if (a === b) return 2;
    if (a === 'abstain' || b === 'abstain') return 1;
    return 0;
  }

  function startQuiz() {
    root.classList.add('q-active');
    i = 0;
    renderQuestion();
  }

  function renderQuestion() {
    const q = Q[i];
    document.getElementById('progress').textContent = 'Frage ' + (i + 1) + ' von ' + Q.length;
    const prev = answers.get(q.id);
    document.getElementById('qtopic').textContent = q.topic;
    document.getElementById('qtext').textContent = q.question;
    document.getElementById('important').checked = !!(prev && prev.important);
    document.getElementById('back').style.visibility = i === 0 ? 'hidden' : 'visible';
  }

  function answer(value) {
    const q = Q[i];
    const important = document.getElementById('important').checked;
    answers.set(q.id, { answer: value, important });
    if (i < Q.length - 1) { i++; renderQuestion(); } else { showResults(); }
  }

  document.getElementById('start').addEventListener('click', startQuiz);
  document.querySelectorAll('.answers button[data-a]').forEach((b) => b.addEventListener('click', () => answer(b.dataset.a)));
  document.getElementById('back').addEventListener('click', () => { if (i > 0) { i--; renderQuestion(); } });
  document.getElementById('restart').addEventListener('click', () => {
    answers.clear();
    ['memberSearch', 'wkSearch'].forEach((id) => { document.getElementById(id).value = ''; });
    ['memberList', 'memberResult', 'wkResult'].forEach((id) => { document.getElementById(id).innerHTML = ''; });
    root.classList.remove('q-active', 'r-active');
    window.scrollTo(0, 0);
  });

  function weight(id) { return answers.get(id) && answers.get(id).important ? 2 : 1; }

  function fractionScores() {
    const fractions = new Set();
    Q.forEach((q) => Object.keys(q.fractions).forEach((f) => fractions.add(f)));
    const rows = [];
    fractions.forEach((f) => {
      let got = 0, max = 0, n = 0;
      Q.forEach((q) => {
        const a = answers.get(q.id);
        const pos = q.fractions[f];
        if (!a || a.answer === 'skip' || !pos) return;
        const w = weight(q.id);
        got += w * points(a.answer, pos);
        max += w * 2;
        n++;
      });
      rows.push({ fraction: f, pct: max ? Math.round((100 * got) / max) : null, n });
    });
    rows.sort((x, y) => (y.pct ?? -1) - (x.pct ?? -1));
    return rows;
  }

  function answeredCount() {
    let k = 0;
    answers.forEach((a) => { if (a.answer !== 'skip') k++; });
    return k;
  }

  function showResults() {
    root.classList.add('r-active');
    const rows = fractionScores();
    document.getElementById('bars').innerHTML = rows.map((r) => `
      <div class="row">
        <span>${esc(fracLabel(r.fraction))}</span>
        <span class="bar"><span style="width:${r.pct ?? 0}%;background:${fracColor(r.fraction)}"></span></span>
        <span class="pct">${r.pct === null ? '–' : r.pct + ' %'}</span>
      </div>`).join('');
    renderBreakdown();
  }

  function esc(s) { return (s == null ? '' : String(s)).replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
  const VOTE_LABEL = { yes: 'Ja', no: 'Nein', abstain: 'Enthaltung', skip: 'übersprungen' };

  function renderBreakdown() {
    const rows = Q.filter((q) => answers.has(q.id)).map((q) => {
      const a = answers.get(q.id);
      const fr = Object.keys(q.fractions).sort((x, y) => fracOrder(x) - fracOrder(y))
        .map((f) => `<span title="${esc(fracLabel(f))}">${esc(fracLabel(f))}: <b>${VOTE_LABEL[q.fractions[f]]}</b></span>`)
        .join(' · ');
      const drs = (q.drucksachen || []).map((d) => `<a href="${esc(d.url)}">${esc(d.number)}</a>`).join(', ');
      return `<tr>
        <td>${esc(q.question)}<div class="note">Eingebracht von: ${esc(q.initiator)}</div>${q.note ? `<div class="note">${esc(q.note)}</div>` : ''}${q.caution ? `<div class="note caution"><b>Vorsicht beim Deuten:</b> ${esc(q.caution)}</div>` : ''}
          <div class="src"><a href="abstimmungen/${esc(q.page)}.html">Zur Abstimmung</a>${drs ? ' · Drucksache ' + drs : ''}</div>
        </td>
        <td>${VOTE_LABEL[a.answer]}${a.important ? ' (wichtig)' : ''}</td>
        <td>${fr}</td>
      </tr>`;
    }).join('');
    document.getElementById('breakdown').innerHTML = rows;
    document.getElementById('answeredCount').textContent = answeredCount() + ' von ' + Q.length + ' Fragen beantwortet';
  }

  // ---- member and Wahlkreis lookup: roll-call questions only ----
  const rollCall = Q.filter((q) => q.kind === 'namentlich');

  function memberScore(pid) {
    let got = 0, max = 0, n = 0;
    rollCall.forEach((q) => {
      const a = answers.get(q.id);
      if (!a || a.answer === 'skip') return;
      const row = q.votes.find((v) => v[0] === pid);
      if (!row) return;
      const w = weight(q.id);
      got += w * points(a.answer, row[1]);
      max += w * 2;
      n++;
    });
    return { pct: max ? Math.round((100 * got) / max) : null, n };
  }

  function memberResultHtml(m) {
    const s = memberScore(m.id);
    const answeredRollCall = rollCall.filter((q) => answers.has(q.id) && answers.get(q.id).answer !== 'skip').length;
    return `<div class="result">
      <b><a href="${esc(m.id)}.html">${esc(m.name)}</a></b> (${esc(fracLabel(m.fraction))})<br>
      ${s.pct === null ? 'Keine der beantworteten namentlichen Abstimmungen liegt für dieses Mitglied vor.'
        : 'Übereinstimmung: <b>' + s.pct + ' %</b>'}
      <div class="note">Von ${answeredRollCall} beantworteten namentlichen Fragen konnten ${s.n} mit diesem Mitglied verglichen werden (von ${answeredCount()} beantworteten Fragen insgesamt; Handzeichen-Abstimmungen zählen nur bei den Fraktionen).</div>
    </div>`;
  }

  (function setupLookup() {
    const q = document.getElementById('memberSearch'), list = document.getElementById('memberList');
    const out = document.getElementById('memberResult');
    const wkInput = document.getElementById('wkSearch'), wkOut = document.getElementById('wkResult');
    q.addEventListener('input', () => {
      const words = q.value.trim().toLowerCase();
      out.innerHTML = '';
      if (words.length < 2) { list.innerHTML = ''; return; }
      const hits = MEMBERS.filter((m) => m.name.toLowerCase().includes(words)).slice(0, 12);
      list.innerHTML = hits.map((m) => `<button type="button" data-id="${esc(m.id)}">${esc(m.name)} (${esc(fracLabel(m.fraction))})</button>`).join('');
      list.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
        const m = MEMBERS.find((x) => x.id === b.dataset.id);
        out.innerHTML = memberResultHtml(m);
        list.innerHTML = '';
        q.value = m.name;
      }));
    });
    wkInput.addEventListener('input', () => {
      const nr = parseInt(wkInput.value, 10);
      if (!nr) { wkOut.innerHTML = ''; return; }
      const here = MEMBERS.filter((m) => m.wk === nr);
      wkOut.innerHTML = here.length
        ? here.map(memberResultHtml).join('')
        : '<p class="note">Kein Mitglied mit diesem Wahlkreis gefunden.</p>';
    });
  })();
})();
</script>"""  # noqa: E501


def page(questions: list[dict], members: list[dict]) -> str:
    n_roll_call = sum(1 for q in questions if q["kind"] == "namentlich")
    body = f"""<div class="cps">
<h1>Wer stimmt wie ich?</h1>
<p class="lead">{len(questions)} Abstimmungen des 21. Deutschen Bundestages, aus vielen Themen, Gesetzentwürfe der Regierung genauso wie Anträge der Opposition. Beantworte jede Frage mit Ja, Nein, Enthaltung oder überspringe sie, und sieh am Ende, welcher Fraktion deine Antworten am nächsten kommen.</p>
<div class="disclaimer">Deine Antworten bleiben in deinem Browser. Nichts wird gespeichert und nichts wird an einen Server geschickt. Schließt du die Seite, sind die Antworten weg. Die Fraktionslinie zeigt oft die Koalitionsdisziplin, nicht immer die persönliche Meinung jedes einzelnen Mitglieds. Dieser Kompass ist eine Übersicht, keine Wahlempfehlung.</div>
<details class="method">
<summary>So wird gerechnet</summary>
<dl>
<dt>Punkte je Frage</dt><dd>Stimmst du mit einer Fraktion überein (beide Ja, beide Nein, oder beide Enthaltung), gibt es 2 Punkte. Steht auf einer Seite eine Enthaltung und auf der anderen Ja oder Nein, gibt es 1 Punkt. Stehen sich Ja und Nein gegenüber, gibt es 0 Punkte. So rechnet auch der Wahl-O-Mat.</dd>
<dt>Wichtige Fragen</dt><dd>Markierst du eine Frage als „wichtig“, zählen ihre Punkte doppelt – die möglichen Punkte dieser Frage verdoppeln sich ebenso.</dd>
<dt>Übersprungene Fragen</dt><dd>Eine übersprungene Frage zählt nicht mit. Sie verändert weder die erreichten noch die möglichen Punkte.</dd>
<dt>Ergebnis</dt><dd>Für jede Fraktion: erreichte Punkte geteilt durch mögliche Punkte, als Prozentzahl. Hat eine Fraktion bei einer Frage keine Linie (Stimmen waren gleich verteilt) oder hat nicht abgestimmt, zählt die Frage bei dieser Fraktion nicht mit.</dd>
<dt>Einzelne Mitglieder und Wahlkreise</dt><dd>Nur bei namentlichen Abstimmungen ist bekannt, wie jedes einzelne Mitglied gestimmt hat. Der Abgleich mit einem Mitglied oder den Mitgliedern eines Wahlkreises nutzt deshalb nur diese Fragen ({n_roll_call} von {len(questions)}), nicht die Abstimmungen per Handzeichen. Es gibt keine Rangliste: Ergebnisse erscheinen nur für ein Mitglied oder einen Wahlkreis, das oder den du selbst eingibst.</dd>
</dl>
</details>
<div id="intro"><button class="primary" id="start" type="button">Kompass starten</button></div>
<div id="quiz">
  <p class="progress" id="progress"></p>
  <div class="qcard">
    <div class="topic" id="qtopic"></div>
    <div class="qtext" id="qtext"></div>
    <label class="important"><input type="checkbox" id="important"> Diese Frage ist mir wichtig (zählt doppelt)</label>
    <div class="answers">
      <button type="button" data-a="yes">Ja</button>
      <button type="button" data-a="no">Nein</button>
      <button type="button" data-a="abstain">Enthaltung</button>
      <button type="button" class="skip" data-a="skip">überspringen</button>
    </div>
    <div class="nav"><button type="button" id="back">zurück</button></div>
  </div>
</div>
<div id="results">
<h2>Übereinstimmung je Fraktion</h2>
<p class="note" id="answeredCount"></p>
<div class="bars" id="bars"></div>
<h2>So hat jede Fraktion abgestimmt</h2>
<table class="breakdown"><thead><tr><th>Frage</th><th>Deine Antwort</th><th>Fraktionen</th></tr></thead>
<tbody id="breakdown"></tbody></table>
<h2>Ein Mitglied oder einen Wahlkreis vergleichen</h2>
<p class="note">Nur namentliche Abstimmungen zeigen, wie ein einzelnes Mitglied gestimmt hat. Es gibt keine Rangliste – nur das Ergebnis für das Mitglied oder den Wahlkreis, das oder den du eingibst.</p>
<div class="lookup">
  <label for="memberSearch">Mitglied suchen</label><br>
  <input type="search" id="memberSearch" placeholder="Name" autocomplete="off">
  <div class="list" id="memberList"></div>
  <div id="memberResult"></div>
</div>
<div class="lookup">
  <label for="wkSearch">Wahlkreis-Nummer</label><br>
  <input type="number" id="wkSearch" min="1" max="299" placeholder="z. B. 14" autocomplete="off">
  <div id="wkResult"></div>
</div>
<p class="restart"><button type="button" id="restart">Von vorn beginnen</button></p>
</div>
<footer>{FOOTER}</footer>
</div>{SCRIPT}"""  # noqa: E501
    data = {
        "kind": "compass", "questions": questions, "members": members,
        "short": SHORT, "token": TOKEN, "order": list(ORDER),
    }  # fmt: skip
    desc = (f"{len(questions)} ausgewählte Abstimmungen des 21. Deutschen Bundestages als Quiz: Ja, Nein, "
            "Enthaltung oder überspringen, und sehen, welcher Fraktion man am nächsten kommt. Läuft vollständig "
            "im Browser, ohne Speicherung.")  # fmt: skip
    return shell(root="", kind="p-compass", active=None, title="Wer stimmt wie ich?", desc=desc,
                 head=STYLE, body=body, data=data)  # fmt: skip


def questions(decisions: list[dict], members: dict[str, list[list]]) -> list[dict]:
    """The quiz's questions; empty below MIN_QUESTIONS candidates that are both selected and approved."""
    qs = build_questions(candidates(), decisions, members)
    return qs if len(qs) >= MIN_QUESTIONS else []


def write(out, qs: list[dict], cards: list[dict]) -> dict[str, int]:
    """Write kompass.html from `questions()`; nothing when that is empty."""
    if not qs:
        return {}
    (out / "kompass.html").write_text(page(qs, member_index(cards)), encoding="utf-8")
    return {"kompass": 1}
