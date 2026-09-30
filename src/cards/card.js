// Renders one card page from CARD (this person) and META (shared facts). German UI, see docs/plan.md.
// Speeches, votes and Drucksachen are not rendered here: facts.py writes the Reden, Abstimmungen and Drucksachen
// tabs into the page (D13), and this script only shows them and filters their rows.
'use strict';

const REPO = 'https://github.com/jan-c-buchkremer/bundestag-mdb-cards';
const FRACTION_COLORS = { 'CDU/CSU': '--cdu', 'SPD': '--spd', 'AfD': '--afd', 'BÜNDNIS 90/DIE GRÜNEN': '--gru', 'Die Linke': '--lin', 'fraktionslos': '--frl' };
const STATES = { BW: 'Baden-Württemberg', BY: 'Bayern', BE: 'Berlin', BB: 'Brandenburg', HB: 'Bremen', HH: 'Hamburg', HE: 'Hessen', MV: 'Mecklenburg-Vorpommern',
  NI: 'Niedersachsen', NW: 'Nordrhein-Westfalen', RP: 'Rheinland-Pfalz', SL: 'Saarland', SN: 'Sachsen', ST: 'Sachsen-Anhalt', SH: 'Schleswig-Holstein', TH: 'Thüringen' };
// Land codes of the Stammdaten before WP 18, incl. Länder of the early Wahlperioden; "*" markers stay empty
const OLD_STATES = { BAY: 'Bayern', BLN: 'Berlin', BLW: 'Berlin (West)', BRA: 'Brandenburg', BRE: 'Bremen', BWG: 'Baden-Württemberg', HBG: 'Hamburg',
  HES: 'Hessen', MBV: 'Mecklenburg-Vorpommern', NDS: 'Niedersachsen', NRW: 'Nordrhein-Westfalen', RPF: 'Rheinland-Pfalz', SAA: 'Sachsen-Anhalt',
  SAC: 'Sachsen', SLD: 'Saarland', SWH: 'Schleswig-Holstein', 'THÜ': 'Thüringen', BAD: 'Baden', WBB: 'Württemberg-Baden', WBH: 'Württemberg-Hohenzollern' };
const stateName = s => STATES[s] || OLD_STATES[s] || '';
const MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
const VOTE = { yes: 'Ja', no: 'Nein', abstain: 'Enthaltung', absent: 'nicht abgestimmt', invalid: 'ungültig' };
const GOVERNMENT = /Bundeskanzler|Bundesminister|Staatssekretär|Staatsminister/;
const PRESIDIUM = /präsident/i;

const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const fractionColor = f => FRACTION_COLORS[f] ? css(FRACTION_COLORS[f]) : css('--reg');
const n = x => x.toLocaleString('de-DE');
const longDate = d => `${+d.slice(8, 10)}. ${MONTHS[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}`;
const shortDate = d => `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}`;
const plural = (k, one, many) => `${n(k)} ${k === 1 ? one : many}`;
const period = (from, to) => to ? `${shortDate(from)} – ${shortDate(to)}` : from ? `seit ${shortDate(from)}` : '';
// a fraction's name, linked to its Fraktion page (gremien.py builds fraktionen/<token>.html for the six fractions)
const fractionLink = f => FRACTION_COLORS[f] ? `<a href="fraktionen/${FRACTION_COLORS[f].slice(2)}.html">${esc(f)}</a>` : esc(f);
// a committee or other Gremium the card lists (data.py adds "slug"), linked to its gremien/<slug>.html page
const bodyLink = x => x.slug ? `<a href="gremien/${esc(x.slug)}.html">${esc(x.name)}</a>` : esc(x.name);
// the speech page is the rede's; a part of it (a Zwischenfrage, a turn in the Befragung) is an anchor there
// the first speech in the Laufbahn tab links its text page (the speech itself is on the Reden tab, facts.py)
const textLink = s => { const r = s.id.replace(/-\d+$/, ''); return `<a href="reden/${encodeURIComponent(r.replaceAll('/', '-'))}.html${r === s.id ? '' : '#' + encodeURIComponent(s.id)}" title="Der Text im Protokoll">Text</a>`; };

const C = CARD;
const member = C.kind === 'member';
const current = xs => xs.filter(x => !x.to);
const offices = current(C.offices);
const today = new Date().toISOString().slice(0, 10);
// offices in the federal government (foundation government_role: Wikidata, Stammdaten, protocol evidence)
const ended = o => !o.evidence && o.to && o.to < today;  // protocol evidence has no end date, only a last sighting
const govNow = C.government.filter(o => !ended(o));
const govOffice = govNow.length ? { role: govNow[0].office } : offices.find(o => GOVERNMENT.test(o.role));
const presidium = offices.find(o => PRESIDIUM.test(o.role));
const votesCast = C.votes.filter(v => v.vote in { yes: 1, no: 1, abstain: 1 });
const withLine = votesCast.filter(v => v.line);
const deviations = C.votes.filter(v => v.deviates);
const questions = C.befragung.filter(b => !b.role), answers = C.befragung.filter(b => b.role);
const fsQuestions = C.fragestunde.filter(b => !b.role), fsAnswers = C.fragestunde.filter(b => b.role);
const byDateDesc = (a, b) => (b.date + b.id).localeCompare(a.date + a.id);
const ACTIVITY = { 'Antrag': ['Antrag', 'Anträge'], 'Kleine Anfrage': ['Kleine Anfrage', 'Kleine Anfragen'], 'Entschließungsantrag': ['Entschließungsantrag', 'Entschließungsanträge'],
  'Änderungsantrag': ['Änderungsantrag', 'Änderungsanträge'], 'Gesetzentwurf': ['Gesetzentwurf', 'Gesetzentwürfe'], 'Frage': ['schriftliche Frage', 'schriftliche Fragen'] };
const SMALL_GROUP = 10;  // up to this many names a Drucksache is a small group's, not the whole fraction's
const documents = C.authored.filter(d => d.activity !== 'Frage'), writtenQuestions = C.authored.filter(d => d.activity === 'Frage');
const hasDip = META.dip.n > 0;
const dipSpan = () => hasDip ? `Drucksachen aus DIP vom ${longDate(META.dip.from)} bis ${longDate(META.dip.to)}` : 'Noch keine Drucksachen aus DIP geladen';
function topSubjects(ds, k = 3) {
  const count = new Map();
  for (const d of ds) for (const s of d.subjects) count.set(s, (count.get(s) || 0) + 1);
  return [...count].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'de')).slice(0, k).map(x => x[0]);
}

// ---------------------------------------------------------------- layer 1: the card
// how the member was elected in 2025, from the Bundeswahlleiterin's files
const pct = x => x.toLocaleString('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' %';
function electionLine(e) {
  const wk = e.number ? `Wahlkreis ${e.number} · ${esc(e.constituency || '')}` : '';
  if (e.via === 'constituency') return `direkt gewählt im ${wk}${e.percent != null ? ` mit ${pct(e.percent)} der Erststimmen` : ''}`;
  const list = `über Platz ${e.list_position} der Landesliste ${STATES[e.list_state] || esc(e.list_state)}`;
  return wk ? `${list} · im ${wk}${e.percent != null ? `: ${pct(e.percent)} der Erststimmen` : ''}` : list;
}

function mandateLines() {
  const m = C.mandate, lines = [];
  if (!member) {
    lines.push(`${esc(C.role || 'Rednerin oder Redner im Plenum')} · kein Mitglied des Bundestages`);
    return lines;
  }
  if (C.election) lines.push(electionLine(C.election));
  else if (m && m.type === 'Direktwahl') lines.push(`direkt gewählt im Wahlkreis ${m.number} · ${esc(m.constituency)} (${STATES[m.state] || m.state})`);
  else if (m) lines.push(`über die Landesliste ${STATES[m.state] || m.state}${m.from > META.sittings.from ? `, nachgerückt am ${longDate(m.from)}` : ''}${m.number ? ` · Wahlkreiskandidatur in ${m.number} ${esc(m.constituency)}` : ''}`);
  else lines.push(`Mitglied spätestens seit ${longDate(C.first_vote)} (laut Abstimmungslisten)`);
  const earlier = C.periods.filter(p => p < META.wp).length;
  const since = earlier ? `zum ${earlier + 1}. Mal im Bundestag (erstmals ${C.since.slice(0, 4)})` : 'zum ersten Mal im Bundestag';
  const born = C.birth_date ? `geboren am ${longDate(C.birth_date)}${C.birth_place ? ` in ${esc(C.birth_place)}` : ''}` : '';
  lines.push([since, born].filter(Boolean).join(' · '));
  return lines;
}

function contextBox() {
  const parts = [];
  if (member && C.mandate && C.mandate.to) {
    const later = [...new Set(C.reden.concat(C.kurz, C.befragung, C.fragestunde).filter(s => s.date > C.mandate.to && s.role).map(s => s.role))];
    const note = later.length ? `Abstimmungen und Ausschüsse enden an diesem Tag. Spätere Reden stammen aus einem anderen Amt: ${later.map(esc).join(', ')}.` : 'Abstimmungen und Ausschüsse enden an diesem Tag.';
    parts.push(`<div class="context left"><b>Aus dem Bundestag ausgeschieden am ${longDate(C.mandate.to)}.</b><div class="note">${note}</div></div>`);
  }
  if (member && !C.in_stammdaten) {
    parts.push(`<div class="context left"><b>Neu im Bundestag.</b><div class="note">Die Stammdaten des Bundestages (${esc(META.stammdaten.doc)}) führen dieses Mandat noch nicht; Wahlkreis, Ausschüsse und Lebensdaten fehlen deshalb vorerst. Die Mitgliedschaft ergibt sich aus den Abstimmungslisten.</div></div>`);
  }
  if (C.government.length) {
    parts.push(officeBlock());
  } else if (govOffice) {
    parts.push(`<div class="context"><b>${esc(govOffice.role)}</b> · ${esc(govOffice.name)} ${period(govOffice.from)}<div class="note">Wer ein Amt in der Bundesregierung hat, spricht im Plenum meist für die Regierung und stellt keine Anfragen an sie. Die Zahlen unten sind vor diesem Hintergrund zu lesen.</div></div>`);
  } else if (presidium) {
    parts.push(`<div class="context"><b>${esc(presidium.role)}</b> ${period(presidium.from)}<div class="note">Das Präsidium leitet die Plenarsitzungen. Sitzungsleitung zählt nicht als Rede.</div></div>`);
  } else if (!member) {
    const land = /\(([^)]+)\)/.exec(C.role || '');
    const why = land ? `Mitglied der Landesregierung ${esc(land[1])}. Mitglieder des Bundesrates dürfen im Bundestag jederzeit sprechen.`
      : GOVERNMENT.test(C.role || '') ? 'Mitglied der Bundesregierung ohne Bundestagsmandat.' : 'Spricht im Bundestag ohne eigenes Mandat.';
    parts.push(`<div class="context"><div class="note">${why} Ohne Mandat gibt es keine Abstimmungen, Ausschüsse oder Drucksachen.</div></div>`);
  }
  const fr = current(C.fraction_roles);
  if (fr.length) parts.push(`<div class="committees"><span class="k">Fraktion</span>${fr.map(r => `${esc(r.role)} der Fraktion ${fractionLink(r.name)}`).join(' · ')}</div>`);
  return parts.join('');
}

const SOURCE = { wikidata: 'Wikidata', stammdaten: 'Stammdaten', protocol: 'Plenarprotokoll' };
function officeWhen(o) {
  const kinds = [...new Map(o.sources.map(x => [x.kind, x])).values()];
  const links = kinds.map(x => x.url ? `<a href="${esc(x.url)}" title="${esc(x.doc)}">${SOURCE[x.kind] || esc(x.kind)}</a>` : SOURCE[x.kind] || esc(x.kind));
  // protocol rows only show that the office was held on the days someone spoke in it, not the term
  // (its to_date is the last sitting that prints the role, not an end of office: the office counts as current)
  if (o.evidence) {
    const last = o.sources.filter(x => x.kind === 'protocol').sort((a, b) => (b.to || b.from || '').localeCompare(a.to || a.from || ''))[0];
    const doc = last && last.url ? `<a href="${esc(last.url)}" title="${esc(last.doc)}">Plenarprotokoll</a>` : 'Plenarprotokoll';
    return `laut ${doc}, zuletzt belegt am ${shortDate(o.to || o.from)}${o.to && o.to !== o.from ? ` · erstmals am ${shortDate(o.from)}` : ''}`;
  }
  return `${period(o.from, o.to)} · laut ${links.join(', ')}`;
}

function officeBlock() {
  const rows = C.government.map(o => `<div class="office${ended(o) ? ' ended' : ''}"><b>${esc(o.office)}</b>${o.department && !o.office.includes(o.department) ? ` <span class="dep">· ${esc(o.department)}</span>` : ''}<div class="when">${officeWhen(o)}</div></div>`);
  const civil = C.government.every(o => o.kind === 'beamteter_sts');
  const note = civil ? 'Beamtete Staatssekretärinnen und Staatssekretäre leiten ein Ministerium mit, gehören aber nicht der Bundesregierung an und sitzen nicht auf der Regierungsbank.'
    : member ? 'Wer ein Amt in der Bundesregierung hat, spricht im Plenum meist für die Regierung und stellt keine Anfragen an sie. Die Zahlen unten sind vor diesem Hintergrund zu lesen.'
    : 'Mitglied der Bundesregierung ohne Bundestagsmandat: Regierungsmitglieder dürfen im Bundestag jederzeit sprechen.';
  return `<div class="context govbox"><span class="k">${civil ? 'Bundesverwaltung' : govNow.length ? 'Bundesregierung' : 'Früher in der Bundesregierung'}</span>${rows.join('')}<div class="note">${note}${member ? '' : ' Ohne Mandat gibt es keine Abstimmungen, Ausschüsse oder Drucksachen.'}</div></div>`;
}

function committeeLine() {
  const cs = current(C.committees);
  if (!cs.length) return '';
  const rank = c => /Vorsitz/.test(c.role) ? 0 : /Obfrau|Obmann/.test(c.role) ? 1 : /Ordentlich/.test(c.role) ? 2 : 3;
  const label = c => /Stellvertretende[rs]? Vorsitz/.test(c.role) ? 'stv. Vorsitz' : /Vorsitz/.test(c.role) ? 'Vorsitz' : /Obfrau|Obmann/.test(c.role) ? c.role : /Stellvertretendes/.test(c.role) ? 'stv. Mitglied' : '';
  const best = new Map();  // one line per committee, with the highest role (Obmann and member rows both exist)
  for (const c of cs) if (!best.has(c.short) || rank(c) < rank(best.get(c.short))) best.set(c.short, c);
  const items = [...best.values()].sort((a, b) => rank(a) - rank(b)).map(c => `${c.slug ? `<a href="gremien/${esc(c.slug)}.html">${esc(c.short)}</a>` : esc(c.short)}${label(c) ? ` <span class="faint">(${label(c)})</span>` : ''}`);
  return `<div class="committees"><span class="k">Ausschüsse</span>${items.join(' · ')}</div>`;
}

function facts() {
  const li = [];
  const reden = C.reden.length;
  if (reden) li.push(`Hat <a href="#reden"><b>${plural(reden, 'Rede', 'Reden')}</b> im Plenum gehalten</a>.`);
  else if (presidium) li.push('Hat keine Rede gehalten, leitet aber als Mitglied des Präsidiums Sitzungen.');
  else li.push('Hat in dieser Wahlperiode noch keine Rede im Plenum gehalten.');
  if (answers.length) li.push(`Hat in der <a href="#reden-befragung">Regierungsbefragung <b>${n(answers.length)}-mal</b> für die Bundesregierung geantwortet</a>.`);
  if (questions.length) li.push(`Hat in der <a href="#reden-befragung">Regierungsbefragung <b>${plural(questions.length, 'Frage', 'Fragen')}</b> gestellt</a>.`);
  if (fsAnswers.length) li.push(`Hat in der <a href="#reden-fragestunde">Fragestunde <b>${n(fsAnswers.length)}-mal</b> für die Bundesregierung geantwortet</a>.`);
  if (fsQuestions.length) li.push(`Hat in der <a href="#reden-fragestunde">Fragestunde <b>${plural(fsQuestions.length, 'Frage', 'Fragen')}</b> gestellt</a>.`);
  const zf = C.fragen.filter(f => f.kind === 'zwischenfrage').length, ki = C.fragen.length - zf;
  if (C.fragen.length) li.push(`Hat <a href="#reden-fragen">${[zf && `<b>${plural(zf, 'Zwischenfrage', 'Zwischenfragen')}</b>`, ki && `<b>${plural(ki, 'Kurzintervention', 'Kurzinterventionen')}</b>`].filter(Boolean).join(' und ')}</a> in Reden anderer gestellt.`);
  if (member && META.dip.complete) {
    const hint = `<span class="hint">${dipSpan()}. Fraktionsanträge tragen oft die Namen der ganzen Fraktion; die Zahl der Namen steht bei jeder Drucksache.</span>`;
    if (documents.length) {
      const byType = Object.keys(ACTIVITY).filter(a => a !== 'Frage').map(a => [a, documents.filter(d => d.activity === a).length]).filter(x => x[1]);
      const small = documents.filter(d => d.authors && d.authors <= SMALL_GROUP).length;
      const list = byType.map(([a, k]) => `<b>${plural(k, ...ACTIVITY[a])}</b>`);
      li.push(`Hat <a href="#drucksachen">${list.length > 1 ? list.slice(0, -1).join(', ') + ' und ' + list.at(-1) : list[0]}</a> mitgezeichnet${small ? `, davon ${n(small)} mit höchstens ${SMALL_GROUP} Namen` : ''}.${hint}`);
    } else if (!govOffice) li.push(`Steht auf keinem Antrag, keiner Anfrage und keinem Gesetzentwurf als Urheber.${hint}`);
    if (writtenQuestions.length) li.push(`Hat <a href="#drucksachen-fragen"><b>${plural(writtenQuestions.length, ...ACTIVITY.Frage)}</b> an die Bundesregierung gestellt</a>.`);
    const topics = topSubjects(C.authored);
    if (topics.length) li.push(`Häufigste Sachgebiete der eigenen Drucksachen: <a href="#drucksachen">${topics.map(esc).join(', ')}</a>.<span class="hint">Sachgebiete vergibt der Bundestag selbst (DIP).</span>`);
  }
  if (member && C.aw && C.aw.questions) {
    const hint = `<span class="hint">Alle Fragen seit Beginn des Profils, nicht nur in dieser Wahlperiode; Stand ${shortDate(C.aw.retrieved)}.</span>`;
    // abgeordnetenwatch leaves the answered count empty on some profiles (119 of 630): no number is better than a guessed 0
    li.push(C.aw.answered == null
      ? `Hat auf <a href="${esc(C.aw.url)}">abgeordnetenwatch.de</a> <b>${plural(C.aw.questions, 'Bürgerfrage', 'Bürgerfragen')}</b> erhalten; wie viele beantwortet sind, gibt die Plattform nicht an.${hint}`
      : `Hat auf <a href="${esc(C.aw.url)}">abgeordnetenwatch.de</a> <b>${n(C.aw.answered)} von ${plural(C.aw.questions, 'Bürgerfrage', 'Bürgerfragen')}</b> beantwortet.${hint}`);
  }
  if (member && C.votes.length) {
    const hint = `<span class="hint">${META.votes} namentliche Abstimmungen seit ${longDate(META.sittings.from)}. Die meisten Beschlüsse fallen per Handzeichen und werden nur je Fraktion festgehalten.</span>`;
    if (C.fraction === 'fraktionslos' || !withLine.length) li.push(`Hat bei <a href="#abstimmungen"><b>${plural(votesCast.length, 'namentlichen Abstimmung', 'namentlichen Abstimmungen')}</b> eine Stimme abgegeben</a>; als fraktionsloses Mitglied ohne Fraktionslinie.${hint}`);
    else if (deviations.length) li.push(`Stimmte bei <a href="#abstimmungen"><b>${n(deviations.length)} von ${n(withLine.length)}</b> namentlichen Abstimmungen anders als die Mehrheit der eigenen Fraktion</a>.${hint}`);
    else li.push(`Stimmte bei <a href="#abstimmungen">allen <b>${n(withLine.length)}</b> namentlichen Abstimmungen mit eigener Stimme</a> wie die Mehrheit der eigenen Fraktion.${hint}`);
  }
  return `<ul class="facts">${li.map(x => `<li>${x}</li>`).join('')}</ul>`;
}

function lastSpeech() {
  const s = C.reden.slice().sort(byDateDesc)[0];
  if (!s) return '';
  return `<div class="last"><span class="k">Zuletzt im Plenum</span>${longDate(s.date)} · <a href="#reden">${esc(s.title)}</a></div>`;
}

function renderCard() {
  const initials = (C.first_name[0] || '') + (C.last_name[0] || '');
  const fraction = member ? (C.fraction || 'fraktionslos') : null;
  const pill = fraction ? `<span class="pill"><span class="dot" style="background:${fractionColor(fraction)}"></span>${fractionLink(fraction)}</span>`
    : '<span class="pill"><span class="dot" style="background:var(--reg)"></span>ohne Mandat</span>';
  document.getElementById('card').innerHTML = `
    <div class="top">
      <div class="photo">${esc(initials)}${C.photo ? `<img src="fotos/${encodeURIComponent(C.id)}.jpg" alt="Foto: ${esc(C.name)}" onerror="this.remove()">` : ''}</div>
      <div class="who">
        <h1>${esc(C.name)}</h1>
        <div style="margin-bottom:8px">${pill}</div>
        <div class="lines">${mandateLines().map(l => `<div>${l}</div>`).join('')}</div>
        ${C.photo ? `<div class="credit">Foto: ${C.photo.url ? `<a href="${esc(C.photo.url)}">${esc(C.photo.credit || 'Quelle')}</a>` : esc(C.photo.credit)}</div>` : ''}
      </div>
    </div>
    ${contextBox()}${committeeLine()}${facts()}${lastSpeech()}`;
}

// ---------------------------------------------------------------- layer 2: tabs
const heard = C.reden.length + C.kurz.length + C.fragen.length + C.befragung.length + C.fragestunde.length;
const TABS = [
  // a card without a mandate shows only the sections that have data (a beamteter Staatssekretär may never speak)
  ...(member || heard ? [['reden', 'Reden', () => C.reden.length, wireReden]] : []),
  ...(member ? [
    ['abstimmungen', 'Abstimmungen', () => C.votes.length, el => wireCheck(el, 'data-dev')],
    ['drucksachen', 'Drucksachen', () => C.authored.length, el => wireCheck(el, 'data-small')],
    ['ausschuesse', 'Ausschüsse & Funktionen', () => C.committees.length + C.offices.length, renderMemberships],
    ...(C.side_jobs.length ? [['nebentaetigkeiten', 'Nebentätigkeiten', () => C.side_jobs.length, renderSideJobs]] : []),
    ['laufbahn', 'Laufbahn', () => C.career.length, renderCareer],
  ] : []),
  ...(C.plenum && (member || C.plenum.made.length || Object.keys(C.plenum.received).length) ? [['plenum', 'Im Plenum', () => C.plenum.made.length, renderPlenum]] : []),
  ['quellen', 'Quellen', () => '', renderSources],
];

function list(rows, empty, limit = 25) {
  if (!rows.length) return `<div class="rows"><div class="empty">${empty}</div></div>`;
  const id = 'l' + Math.random().toString(36).slice(2, 8);
  const more = rows.length > limit ? `<button class="more" data-for="${id}">Alle ${n(rows.length)} zeigen</button>` : '';
  return `<div class="rows" id="${id}">${rows.map((r, i) => i < limit ? r : r.replace('class="row', 'hidden class="row')).join('')}${more}</div>`;
}

// the fact tabs written by facts.py: filter their rows in place. A cut row (`data-cut`) waits for "Alle N zeigen"
// while no filter is set; a filter shows every match, and clearing it restores the cut
function filterRows(el, keep, all) {
  el.querySelectorAll('.rows > .sp, .rows > .dec, .rows > .row').forEach(r => {
    r.hidden = !keep(r) || (all && r.hasAttribute('data-cut'));
  });
}

function wireReden(el) {
  const input = el.querySelector('input.fq');
  if (input) input.oninput = () => {
    const q = input.value.trim().toLowerCase();
    filterRows(el, r => !q || (r.dataset.q || '').includes(q) || r.textContent.toLowerCase().includes(q), !q);
  };
}

function wireCheck(el, attr) {
  const box = el.querySelector('input.fonly');
  if (box) box.onchange = () => filterRows(el, r => !box.checked || r.hasAttribute(attr), !box.checked);
}

function renderMemberships(el) {
  const block = (title, xs, fmt) => {
    if (!xs.length) return '';
    const sorted = xs.slice().sort((a, b) => (!!a.to - !!b.to) || (a.from || '').localeCompare(b.from || ''));
    return `<h2>${title} <span class="n">${xs.length}</span></h2><div class="rows memb">${sorted.map(x => `
      <div class="row${x.to ? ' ended' : ''}"><div class="t">${fmt(x)}</div><div class="d">${period(x.from, x.to)}</div></div>`).join('')}</div>`;
  };
  const withRole = x => `${esc(x.name)}${x.role ? `<div class="sub">${esc(x.role)}</div>` : ''}`;
  const fractionRow = x => `${fractionLink(x.name)}${x.role ? `<div class="sub">${esc(x.role)}</div>` : ''}`;
  const bodyRow = x => `${bodyLink(x)}${x.role ? `<div class="sub">${esc(x.role)}</div>` : ''}`;
  el.innerHTML = `
    <p class="explain">Stand der Stammdaten des Bundestages: ${esc(META.stammdaten.doc)}. Spätere Wechsel fehlen hier, bis der Bundestag die Stammdaten erneuert.</p>
    ${block('Ämter', C.offices, withRole)}
    ${block('Fraktion', C.fractions, fractionRow)}
    ${block('Ausschüsse', C.committees, bodyRow)}
    ${block('Weitere Gremien', C.other, bodyRow)}
    ${!C.offices.length && !C.fractions.length && !C.committees.length && !C.other.length ? '<div class="rows"><div class="empty">Keine Einträge in den Stammdaten.</div></div>' : ''}`;
}

// "21/94" -> the sitting's PDF, as the foundation builds sitting.pdf_url
const protocolPdf = s => { const [wp, nr] = s.split('/'); return `https://dserver.bundestag.de/btp/${wp}/${wp}${nr.padStart(3, '0')}.pdf`; };
const FRACTION_ORDER = ['CDU/CSU', 'AfD', 'SPD', 'BÜNDNIS 90/DIE GRÜNEN', 'Die Linke', 'fraktionslos'];
const SHORT = { 'BÜNDNIS 90/DIE GRÜNEN': 'Grüne', 'Die Linke': 'Linke' };

function renderPlenum(el) {
  const R = C.plenum.received;
  const fr = FRACTION_ORDER.filter(f => R[f]).concat(Object.keys(R).filter(f => !FRACTION_ORDER.includes(f)));
  const cell = x => `<td class="num">${x ? n(x) : '<span class="faint">–</span>'}</td>`;
  const table = fr.length ? `<div class="rows" style="overflow-x:auto"><table class="plenum">
    <thead><tr><th>Fraktion</th><th>Beifall der Fraktion</th><th>Beifall einzelner Abg.</th><th>Zurufe</th><th>Lachen, Heiterkeit</th><th>Widerspruch</th></tr></thead>
    <tbody>${fr.map(f => `<tr${f === C.fraction ? ' class="own"' : ''}><td><span class="dot" style="background:${fractionColor(f)};width:7px;height:7px;margin-right:6px"></span>${esc(SHORT[f] || f)}${f === C.fraction ? ' <span class="faint">(eigene)</span>' : ''}</td>${cell(R[f].beifall)}${cell(R[f].beifall_members)}${cell(R[f].zurufe)}${cell(R[f].lachen)}${cell(R[f].widerspruch)}</tr>`).join('')}</tbody>
  </table></div>${C.plenum.house ? `<p class="explain" style="margin-top:8px">Dazu ${n(C.plenum.house)}-mal Beifall im ganzen Haus.</p>` : ''}` : '<div class="rows"><div class="empty">Keine Reaktionen im Protokoll.</div></div>';
  const made = C.plenum.made.slice().sort(byDateDesc).map(z => `
    <div class="row"><div class="d">${shortDate(z.date)}</div>
      <div class="t">${z.text ? `„${esc(z.text)}“` : `<span class="muted">${z.kind === 'gegenruf' ? 'Gegenruf' : 'Zuruf'} ohne Wortlaut</span>`}
        <div class="sub">${z.kind === 'gegenruf' ? 'Gegenruf' : 'Zwischenruf'} ${z.to ? `an <a href="${esc(z.to)}.html">${esc(z.to_name)}</a>` : `in der Rede von <a href="${esc(z.speaker)}.html">${esc(z.speaker_name)}</a>`} · ${esc(z.title)}</div></div>
      <div class="l"><a href="${protocolPdf(z.sitting)}" title="BT-PlPr. ${esc(z.sitting)}, Rede ${esc(z.id)}">Protokoll</a></div></div>`);
  el.innerHTML = `
    <p class="explain">Das Plenarprotokoll hält fest, wer Beifall spendet, dazwischenruft, lacht oder widerspricht. Die Tabelle zählt diese Vermerke während eigener Redebeiträge: „Beifall bei der SPD“ ist Beifall der Fraktion, „Beifall bei Abgeordneten der SPD“ Beifall einzelner. Gezählt ist nur, was direkt auf eigene Worte folgt; Vermerke nach Worten der Sitzungsleitung (etwa Beifall für die nächste Person am Pult oder nach einem Ordnungsruf) fehlen. Das Protokoll hält fest, wann Beifall fällt, nicht wem er gilt: Er kann auch einem Zwischenruf gelten. Wie oft etwas vermerkt wird, hängt zudem davon ab, wie lang und wie umstritten eine Debatte war; es ist kein Maß für Zustimmung.</p>
    <h2 id="plenum-reaktionen">Vermerke während eigener Beiträge</h2>${table}
    <h2 id="plenum-zurufe">Eigene Zwischenrufe <span class="n">${n(made.length)}</span></h2>
    <p class="explain">Zurufe, die das Protokoll mit Namen verzeichnet, meist mit Wortlaut.</p>
    ${list(made, 'Keine namentlich protokollierten Zwischenrufe.')}`;
}

function renderCareer(el) {
  const where = m => m.type === 'Direktwahl' ? `direkt gewählt im Wahlkreis ${m.number} · ${esc(m.constituency)}`
    : m.type === 'Landesliste' ? `Landesliste ${esc(stateName(m.state))}${m.number ? ` · Wahlkreiskandidatur in ${m.number} ${esc(m.constituency)}` : ''}`
    : m.type === 'Volkskammer' ? 'von der Volkskammer entsandt' : esc(m.type || '');
  const gaps = [];
  for (let i = 1; i < C.career.length; i++) if (C.career[i].wp - C.career[i - 1].wp > 1) gaps.push(`zwischen der ${C.career[i - 1].wp}. und der ${C.career[i].wp}. Wahlperiode`);
  const rows = C.career.slice().reverse().map(m => `<div class="row"><div class="t">${m.wp}. Wahlperiode<div class="sub">${m.wp === META.wp && C.election ? electionLine(C.election) + (C.election.via === 'constituency' && C.election.list_position ? `; abgesichert auf Platz ${C.election.list_position} der Landesliste ${STATES[C.election.list_state] || esc(C.election.list_state)}` : '') : where(m)}</div></div><div class="d">${period(m.from, m.to)}</div></div>`);
  // WP 21 at a glance: first speech (careers.annotate), fraction changes, government offices
  const now = [];
  const fs = C.first_speech;
  if (fs) now.push(`<div class="row"><div class="t">Erste Rede in der ${META.wp}. Wahlperiode${fs.maiden && C.periods.length <= 1 ? ' · Jungfernrede' : ''}<div class="sub">${esc(fs.title || '')}${fs.maiden ? ' · laut Sitzungsleitung die erste Rede' : ''} · ${textLink(fs)}</div></div><div class="d">${shortDate(fs.date)}</div></div>`);
  if (new Set(C.fractions.map(f => f.name)).size > 1 || (C.fractions.length && C.fractions.every(f => f.to) && !(C.mandate && C.mandate.to)))
    C.fractions.forEach(f => now.push(`<div class="row"><div class="t">Fraktion ${fractionLink(f.name)}</div><div class="d">${period(f.from, f.to)}</div></div>`));
  C.government.forEach(o => now.push(`<div class="row"><div class="t">${esc(o.office)}<div class="sub">${officeWhen(o)}</div></div></div>`));
  el.innerHTML = `
    ${now.length ? `<div class="rows memb">${now.join('')}</div>` : ''}
    <p class="explain">Alle Mandate seit der ersten Wahlperiode laut Stammdaten des Bundestages (${esc(META.stammdaten.doc)}).</p>
    ${gaps.length ? `<p class="explain">Nicht im Bundestag ${gaps.join(', ')}.</p>` : ''}
    ${C.in_stammdaten ? '' : `<p class="explain">Das aktuelle Mandat fehlt in diesem Stand der Stammdaten; Mitglied spätestens seit ${longDate(C.first_vote)}.</p>`}
    <div class="rows memb">${rows.join('') || '<div class="empty">Keine Mandate in den Stammdaten.</div>'}</div>`;
}

function renderSideJobs(el) {
  const rows = C.side_jobs.slice().sort((a, b) => (b.changed || '').localeCompare(a.changed || '')).map(j => `
    <div class="row"><div class="d"></div>
      <div class="t">${esc(j.label)}<div class="sub">${[
        j.organization && esc(j.organization), j.category && esc(j.category),
        j.income_range ? `Stufe ${j.income_level}: ${esc(j.income_range)}${j.interval ? ` · ${esc(j.interval)}` : ''}` : j.interval && esc(j.interval),
      ].filter(Boolean).join(' · ')}</div></div>
      <div class="l">${j.url ? `<a href="${esc(j.url)}" title="Der Eintrag als Rohdaten (JSON) bei abgeordnetenwatch.de">Datensatz</a>` : ''}</div></div>`);
  el.innerHTML = `
    <p class="explain">Veröffentlichungspflichtige Angaben nach den Verhaltensregeln des Bundestages, wie der Bundestag sie veröffentlicht; zusammengestellt von ${C.aw ? `<a href="${esc(C.aw.url)}">abgeordnetenwatch.de</a>` : 'abgeordnetenwatch.de'} (CC0). Einkünfte stehen als veröffentlichte Stufe mit ihrer Spanne, nicht als genauer Betrag. Die Karte rechnet nichts zusammen und bringt die Angaben nicht mit Reden oder Abstimmungen in Verbindung.</p>
    ${list(rows, 'Keine Nebentätigkeiten gemeldet.')}`;
}

function renderSources(el) {
  const s = META.stammdaten;
  const issue = `${REPO}/issues/new?title=${encodeURIComponent(`Fehler auf der Karte von ${C.name} (${C.id})`)}`;
  el.innerHTML = `
    <ul class="sources">
      ${member ? `<li><a href="${esc(s.url)}">Stammdaten aller Abgeordneten</a> (${esc(s.doc)}, abgerufen ${shortDate(s.retrieved)}): Person, Mandat, Wahlperioden, Ausschüsse und Ämter. © Deutscher Bundestag</li>` : ''}
      <li>Plenarprotokolle der ${META.wp}. Wahlperiode, ${META.sittings.n} Sitzungen vom ${shortDate(META.sittings.from)} bis ${shortDate(META.sittings.to)}; jede Rede verlinkt auf ihr Protokoll. © Deutscher Bundestag</li>
      ${member ? `<li>Listen der namentlichen Abstimmungen (XLSX und PDF), je Abstimmung verlinkt. © Deutscher Bundestag</li>` : ''}
      ${member && hasDip ? `<li>DIP, Dokumentations- und Informationssystem für Parlamentsmaterialien: Drucksachen, Urheber und Sachgebiete (${META.dip.n} Drucksachen vom ${shortDate(META.dip.from)} bis ${shortDate(META.dip.to)}). © Deutscher Bundestag/Bundesrat – DIP</li>` : ''}
      ${member && META.election.length ? `<li>Bundestagswahl 2025: ${META.election.map(s => `<a href="${esc(s.url)}">${esc(s.doc)}</a>`).join(', ')}. © Die Bundeswahlleiterin, Wiesbaden 2025, <a href="https://www.govdata.de/dl-de/by-2-0">dl-de/by-2-0</a></li>` : ''}
      ${C.government.length ? `<li>Ämter in der Bundesregierung: ${[...new Set(C.government.flatMap(o => o.sources.map(x => x.kind)))].map(k => k === 'wikidata' ? 'Wikidata („Position inne“, CC0 1.0)' : k === 'stammdaten' ? 'Stammdaten des Bundestages' : 'Plenarprotokolle, in denen die Person in diesem Amt spricht').join('; ')}. Jede Angabe oben ist mit ihrer Quelle verlinkt.</li>` : ''}
      ${C.wikidata ? `<li>Wikidata: <a href="https://www.wikidata.org/wiki/${esc(C.wikidata)}">${esc(C.wikidata)}</a> (CC0 1.0)</li>` : ''}
      ${C.aw ? `<li>abgeordnetenwatch.de: <a href="${esc(C.aw.url)}">Profil</a> mit Bürgerfragen und Antworten (Stand ${shortDate(C.aw.retrieved)}, CC0 1.0)</li>` : C.aw_id ? `<li>abgeordnetenwatch.de: <a href="https://www.abgeordnetenwatch.de/api/v2/politicians/${esc(C.aw_id)}">Datensatz ${esc(C.aw_id)}</a> (CC0 1.0)</li>` : ''}
      ${C.photo ? `<li>Foto: ${esc(C.photo.credit || '')}${C.photo.url ? `, <a href="${esc(C.photo.url)}">${/wikimedia/.test(C.photo.url) ? 'Wikimedia Commons' : 'Biografie auf bundestag.de'}</a>` : ''}; verkleinert auf 240 Pixel Breite.</li>` : ''}
      <li>Alle Angaben dieser Seite als <a href="${esc(C.id)}.json">JSON</a>.</li>
    </ul>
    <p class="explain">Die Daten werden mit <a href="https://github.com/jan-c-buchkremer/bundestag-data-foundation">bundestag-data-foundation</a> aus den Originalquellen gesammelt und täglich aktualisiert. Diese Seite wurde am ${shortDate(META.built)} erzeugt. Etwas stimmt nicht? <a href="${issue}">Fehler melden</a>.</p>`;
}

function renderTabs() {
  const want = (location.hash.slice(1) || 'reden');
  const active = TABS.find(t => want === t[0] || want.startsWith(t[0] + '-')) || TABS[0];
  const nav = document.getElementById('tabs');
  nav.innerHTML = `<div class="tabs-in">${TABS.map(([id, label, count]) => {
    const k = count();
    return `<a href="#${id}" class="${id === active[0] ? 'on' : ''}"${id === active[0] ? ' aria-current="page"' : ''}>${label}${k !== '' ? `<span class="n">${n(k)}</span>` : ''}</a>`;
  }).join('')}</div>`;
  const body = document.getElementById('tabbody');
  if (body.dataset.tab !== active[0]) {
    body.dataset.tab = active[0];
    body.querySelectorAll(':scope > .tab').forEach(t => t.classList.remove('on'));
    // a fact tab is in the page already (facts.py); the others are drawn once, the first time they open
    let tab = document.getElementById(`tab-${active[0]}`);
    if (!tab) {
      tab = document.createElement('section');
      tab.className = 'tab';
      tab.id = `tab-${active[0]}`;
      body.append(tab);
    }
    if (!tab.dataset.ready) { tab.dataset.ready = '1'; active[3](tab); }
    tab.classList.add('on');
  }
  // the active tab in view inside the bar, without moving the page
  const strip = nav.firstElementChild, on = strip.querySelector('a.on');
  if (on && (on.offsetLeft < strip.scrollLeft || on.offsetLeft + on.offsetWidth > strip.scrollLeft + strip.clientWidth)) {
    strip.scrollLeft = on.offsetLeft - (strip.clientWidth - on.offsetWidth) / 2;
  }
  fadeTabs();
  if (want !== active[0]) document.getElementById(want)?.scrollIntoView({ block: 'start' });
}

// the tab bar scrolls sideways when it is wider than the page: fade the edge that has more tabs behind it
function fadeTabs() {
  const strip = document.querySelector('#tabs .tabs-in');
  if (!strip) return;
  const nav = strip.parentElement, max = strip.scrollWidth - strip.clientWidth;
  nav.classList.toggle('more-l', strip.scrollLeft > 2);
  nav.classList.toggle('more-r', strip.scrollLeft < max - 2);
}
document.getElementById('tabs').addEventListener('scroll', fadeTabs, true);
window.addEventListener('resize', fadeTabs);
// a vertical mouse wheel scrolls the bar sideways (only while it overflows; the page scrolls otherwise)
document.getElementById('tabs').addEventListener('wheel', e => {
  const strip = e.currentTarget.firstElementChild;
  if (!strip || strip.scrollWidth <= strip.clientWidth || Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return;
  const before = strip.scrollLeft;
  strip.scrollLeft += e.deltaY;
  if (strip.scrollLeft !== before) e.preventDefault();
}, { passive: false });

// switching tabs keeps the page where it is: no jump to an anchor, and a shorter tab does not pull the page up.
// When the bar is stuck at the top, the new tab starts right under it; otherwise the scroll position stays.
document.getElementById('tabs').addEventListener('click', e => {
  const a = e.target.closest('a[href^="#"]');
  if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
  e.preventDefault();
  if (a.classList.contains('on')) return;
  const nav = document.getElementById('tabs');
  const stuck = nav.getBoundingClientRect().top <= 1 && window.scrollY > 0;
  const y = window.scrollY;
  history.pushState(null, '', a.getAttribute('href'));
  const body = document.getElementById('tabbody');
  body.style.minHeight = `${window.innerHeight}px`;  // room below the bar so the position can be kept
  renderTabs();
  if (stuck) {
    const top = body.getBoundingClientRect().top + window.scrollY - nav.offsetHeight - parseFloat(getComputedStyle(nav).marginBottom);
    window.scrollTo(0, Math.min(y, top));
  } else window.scrollTo(0, y);
});

document.addEventListener('click', e => {
  const b = e.target.closest('.more');
  if (b) {
    const box = document.getElementById(b.dataset.for);
    box.querySelectorAll('[data-cut], .row[hidden]').forEach(r => { r.hidden = false; r.removeAttribute('data-cut'); });
    b.remove();
  }
});
// links to a tab from elsewhere on the page (the facts list, "Zuletzt im Plenum"): open it with the bar on top
window.addEventListener('hashchange', () => {
  renderTabs();
  if (TABS.some(t => t[0] === location.hash.slice(1))) document.getElementById('tabs').scrollIntoView({ block: 'start' });
});

renderCard();
renderTabs();
document.getElementById('foot').innerHTML = `Daten: Deutscher Bundestag${member && META.election.length ? ', Die Bundeswahlleiterin' : ''}${C.aw_id ? ', abgeordnetenwatch.de (CC0 1.0)' : ''}${C.government.length ? ', Wikidata (CC0 1.0)' : ''}. Code: <a href="${REPO}">bundestag-mdb-cards</a> (MIT). Keine Rangliste, keine Bewertung: Zahlen stehen immer mit ihrem Zusammenhang.`;
