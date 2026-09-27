// Renders one card page from CARD (this person) and META (shared facts). German UI, see docs/plan.md.
'use strict';

const LANDSCAPE = 'https://jan-c-buchkremer.github.io/bundestag-topic-landscape/';
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
const VOTE_COLORS = { yes: '#4c9a5f', no: '#d0485a', abstain: '#c9a72c', absent: '#d4d4d0' };
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
const isoWeek = d => {
  const t = new Date(Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)));
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);
  const y = t.getUTCFullYear(), w = Math.ceil(((t - Date.UTC(y, 0, 1)) / 864e5 + 1) / 7);
  return `${y}-W${String(w).padStart(2, '0')}`;
};
const mapLink = s => s.on_map ? `<a href="${LANDSCAPE}${isoWeek(s.date)}.html#rede=${encodeURIComponent(s.id)}" title="Diese Rede in der Themenlandschaft der Woche">Karte</a>` : '';
const pdfLink = s => `<a href="${esc(s.pdf)}" title="${esc(s.cite)}, Rede ${esc(s.id)}">Protokoll</a>`;

const C = CARD;
const member = C.kind === 'member';
const current = xs => xs.filter(x => !x.to);
const offices = current(C.offices);
const govOffice = offices.find(o => GOVERNMENT.test(o.role));
const presidium = offices.find(o => PRESIDIUM.test(o.role));
const votesCast = C.votes.filter(v => v.vote in { yes: 1, no: 1, abstain: 1 });
const withLine = votesCast.filter(v => v.line);
const deviations = C.votes.filter(v => v.deviates);
const questions = C.befragung.filter(b => !b.role), answers = C.befragung.filter(b => b.role);
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
    const later = [...new Set(C.reden.concat(C.kurz, C.befragung).filter(s => s.date > C.mandate.to && s.role).map(s => s.role))];
    const note = later.length ? `Abstimmungen und Ausschüsse enden an diesem Tag. Spätere Reden stammen aus einem anderen Amt: ${later.map(esc).join(', ')}.` : 'Abstimmungen und Ausschüsse enden an diesem Tag.';
    parts.push(`<div class="context left"><b>Aus dem Bundestag ausgeschieden am ${longDate(C.mandate.to)}.</b><div class="note">${note}</div></div>`);
  }
  if (member && !C.in_stammdaten) {
    parts.push(`<div class="context left"><b>Neu im Bundestag.</b><div class="note">Die Stammdaten des Bundestages (${esc(META.stammdaten.doc)}) führen dieses Mandat noch nicht; Wahlkreis, Ausschüsse und Lebensdaten fehlen deshalb vorerst. Die Mitgliedschaft ergibt sich aus den Abstimmungslisten.</div></div>`);
  }
  if (govOffice) {
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
  if (fr.length) parts.push(`<div class="committees"><span class="k">Fraktion</span>${fr.map(r => `${esc(r.role)} der Fraktion ${esc(r.name)}`).join(' · ')}</div>`);
  return parts.join('');
}

function committeeLine() {
  const cs = current(C.committees);
  if (!cs.length) return '';
  const rank = c => /Vorsitz/.test(c.role) ? 0 : /Obfrau|Obmann/.test(c.role) ? 1 : /Ordentlich/.test(c.role) ? 2 : 3;
  const label = c => /Stellvertretende[rs]? Vorsitz/.test(c.role) ? 'stv. Vorsitz' : /Vorsitz/.test(c.role) ? 'Vorsitz' : /Obfrau|Obmann/.test(c.role) ? c.role : /Stellvertretendes/.test(c.role) ? 'stv. Mitglied' : '';
  const best = new Map();  // one line per committee, with the highest role (Obmann and member rows both exist)
  for (const c of cs) if (!best.has(c.short) || rank(c) < rank(best.get(c.short))) best.set(c.short, c);
  const items = [...best.values()].sort((a, b) => rank(a) - rank(b)).map(c => `${esc(c.short)}${label(c) ? ` <span class="faint">(${label(c)})</span>` : ''}`);
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
  const pill = fraction ? `<span class="pill"><span class="dot" style="background:${fractionColor(fraction)}"></span>${esc(fraction)}</span>`
    : '<span class="pill"><span class="dot" style="background:var(--reg)"></span>ohne Mandat</span>';
  document.getElementById('card').innerHTML = `
    <div class="top">
      <div class="photo" title="Fotos folgen, sobald die Lizenz der Bundestagsfotos geklärt ist">${esc(initials)}</div>
      <div class="who">
        <h1>${esc(C.name)}</h1>
        <div style="margin-bottom:8px">${pill}</div>
        <div class="lines">${mandateLines().map(l => `<div>${l}</div>`).join('')}</div>
      </div>
    </div>
    ${contextBox()}${committeeLine()}${facts()}${lastSpeech()}`;
}

// ---------------------------------------------------------------- layer 2: tabs
const TABS = [
  ['reden', 'Reden', () => C.reden.length, renderReden],
  ...(member ? [
    ['abstimmungen', 'Abstimmungen', () => C.votes.length, renderVotes],
    ['drucksachen', 'Drucksachen', () => C.authored.length, renderDocuments],
    ['ausschuesse', 'Ausschüsse & Funktionen', () => C.committees.length + C.offices.length, renderMemberships],
    ['laufbahn', 'Laufbahn', () => C.career.length, renderCareer],
  ] : []),
  ['quellen', 'Quellen', () => '', renderSources],
];

function list(rows, empty, limit = 25) {
  if (!rows.length) return `<div class="rows"><div class="empty">${empty}</div></div>`;
  const id = 'l' + Math.random().toString(36).slice(2, 8);
  const more = rows.length > limit ? `<button class="more" data-for="${id}">Alle ${n(rows.length)} zeigen</button>` : '';
  return `<div class="rows" id="${id}">${rows.map((r, i) => i < limit ? r : r.replace('class="row', 'hidden class="row')).join('')}${more}</div>`;
}

function renderReden(el) {
  const q = (el.dataset.q || '').toLowerCase();
  const match = s => !q || (s.title + ' ' + s.date + ' ' + (s.speaker_name || '')).toLowerCase().includes(q);
  const who = i => `<a href="${esc(i.person)}.html">${esc(i.name)}</a>${i.kind === 'kurzintervention' ? ' (Kurzintervention)' : ''}`;
  const reden = C.reden.filter(match).sort(byDateDesc).map(s => `
    <div class="row"><div class="d">${shortDate(s.date)}</div>
      <div class="t">${esc(s.title)}<div class="sub">${[
        s.role && esc(s.role), plural(s.words, 'Wort', 'Wörter'), s.applause && `${n(s.applause)}× Beifall`,
        s.interruptions.length && `${s.interruptions.length === 1 ? 'Zwischenfrage' : 'Zwischenfragen'} von ${s.interruptions.map(who).join(', ')}`,
      ].filter(Boolean).join(' · ')}</div></div>
      <div class="l">${mapLink(s)}${pdfLink(s)}</div></div>`);
  const fragen = C.fragen.filter(match).sort(byDateDesc).map(f => `
    <div class="row"><div class="d">${shortDate(f.date)}</div>
      <div class="t">${f.kind === 'kurzintervention' ? 'Kurzintervention' : 'Zwischenfrage'} an <a href="${esc(f.speaker)}.html">${esc(f.speaker_name)}</a><div class="sub">${esc(f.title)}</div></div>
      <div class="l">${pdfLink(f)}</div></div>`);
  const kurz = C.kurz.filter(match).sort(byDateDesc).map(s => `
    <div class="row"><div class="d">${shortDate(s.date)}</div>
      <div class="t">${esc(s.title)}<div class="sub">${[s.role && esc(s.role), plural(s.words, 'Wort', 'Wörter')].filter(Boolean).join(' · ')}</div></div>
      <div class="l">${pdfLink(s)}</div></div>`);
  const bef = C.befragung.filter(match).sort(byDateDesc).map(b => `
    <div class="row"><div class="d">${shortDate(b.date)}</div>
      <div class="t">${b.role ? `Antwort als ${esc(b.role)}` : 'Frage an die Bundesregierung'}<div class="sub">${plural(b.words, 'Wort', 'Wörter')}</div></div>
      <div class="l">${mapLink(b)}${pdfLink(b)}</div></div>`);
  el.innerHTML = `
    <div class="tools"><input type="search" placeholder="Reden durchsuchen: Tagesordnungspunkt, Datum …" value="${esc(el.dataset.q || '')}"></div>
    <p class="explain">Eine Rede ist ein Redebeitrag zu einem Tagesordnungspunkt, so wie ihn das Plenarprotokoll führt, mit mindestens 500 Zeichen; Zwischenfragen anderer gehören zur Rede, in der sie gestellt wurden. Die Länge ist in Wörtern angegeben, die Redezeit steht nicht im Protokoll. „Karte“ öffnet die Rede in der Themenlandschaft ihrer Sitzungswoche.</p>
    <h2 id="reden-reden">Reden <span class="n">${n(reden.length)}</span></h2>${list(reden, 'Keine Reden.')}
    ${C.kurz.length ? `<h2 id="reden-kurz">Kurze Wortbeiträge <span class="n">${n(kurz.length)}</span></h2><p class="explain">Beiträge unter 500 Zeichen, etwa ein Amtseid, eine Erklärung zur Abstimmung in einem Satz oder ein Hinweis zur Geschäftsordnung. Sie zählen nicht als Rede, so wie in der Themenlandschaft.</p>${list(kurz, 'Keine Treffer.')}` : ''}
    ${C.fragen.length ? `<h2 id="reden-fragen">Zwischenfragen und Kurzinterventionen <span class="n">${n(fragen.length)}</span></h2>${list(fragen, 'Keine Treffer.')}` : ''}
    ${C.befragung.length ? `<h2 id="reden-befragung">Regierungsbefragung <span class="n">${n(bef.length)}</span></h2><p class="explain">In der Regierungsbefragung ist jede Frage und jede Antwort ein eigener Beitrag im Protokoll; sie zählen deshalb nicht als Reden.</p>${list(bef, 'Keine Treffer.')}` : ''}`;
  const input = el.querySelector('input');
  input.oninput = () => { el.dataset.q = input.value; renderReden(el); const i = el.querySelector('input'); i.focus(); i.setSelectionRange(i.value.length, i.value.length); };
}

function split(t) {
  const total = t.yes + t.no + t.abstain + t.absent;
  return `<div class="split" title="${['yes', 'no', 'abstain', 'absent'].map(k => `${VOTE[k]}: ${t[k]}`).join(', ')}">${['yes', 'no', 'abstain', 'absent'].map(k => `<i style="width:${100 * t[k] / total}%;background:${VOTE_COLORS[k]}"></i>`).join('')}</div>`;
}

function renderVotes(el) {
  const only = el.dataset.only === '1';
  const shown = C.votes.filter(v => !only || v.deviates).slice().sort(byDateDesc);
  const absent = C.votes.filter(v => v.vote === 'absent').length;
  const rows = shown.map(v => {
    const t = v.fraction_tally;
    const line = v.line ? `Fraktion ${esc(v.fraction)} mehrheitlich <b>${VOTE[v.line]}</b>` : v.fraction === 'fraktionslos' ? 'fraktionslos' : `Fraktion ${esc(v.fraction)} ohne klare Mehrheit`;
    return `<div class="row${v.deviates ? ' hi' : ''}"><div class="d">${shortDate(v.date)}</div>
      <div class="t">${esc(v.title)}${v.drucksache ? ` <span class="tag">Drs. ${esc(v.drucksache)}</span>` : ''}
        <div class="sub">${line}${v.fraction !== 'fraktionslos' ? ` (${t.yes} Ja, ${t.no} Nein, ${t.abstain} Enth., ${t.absent} nicht abg.)` : ''} · Bundestag: ${v.result.yes} Ja, ${v.result.no} Nein, ${v.result.abstain} Enth.</div>
        ${v.fraction !== 'fraktionslos' ? split(t) : ''}</div>
      <div class="l"><span class="vote ${v.vote}">${VOTE[v.vote]}</span><div style="margin-top:6px"><a href="${esc(v.pdf || v.xlsx)}">Liste</a></div></div></div>`;
  });
  el.innerHTML = `
    <p class="explain">Namentlich abgestimmt wird nur, wenn eine Fraktion oder 5 % der Mitglieder es verlangen: ${META.votes}-mal seit ${longDate(META.sittings.from)}. Jede Zeile zeigt die eigene Stimme neben der Mehrheit der eigenen Fraktion und dem Ergebnis im ganzen Haus.</p>
    ${absent ? `<p class="explain">„Nicht abgestimmt“ (${n(absent)}-mal) sagt nichts über den Grund: Krankheit, Elternzeit, Dienstreisen und Pairing-Absprachen stehen nicht in den Listen.</p>` : ''}
    <div class="tools"><label><input type="checkbox"${only ? ' checked' : ''}> nur Abweichungen von der Fraktionsmehrheit (${n(deviations.length)})</label></div>
    ${list(rows, only ? 'Keine Abweichungen von der Fraktionsmehrheit.' : 'Keine namentlichen Abstimmungen.', 100)}`;
  el.querySelector('input').onchange = e => { el.dataset.only = e.target.checked ? '1' : ''; renderVotes(el); };
}

function renderMemberships(el) {
  const block = (title, xs, fmt) => {
    if (!xs.length) return '';
    const sorted = xs.slice().sort((a, b) => (!!a.to - !!b.to) || (a.from || '').localeCompare(b.from || ''));
    return `<h2>${title} <span class="n">${xs.length}</span></h2><div class="rows memb">${sorted.map(x => `
      <div class="row${x.to ? ' ended' : ''}"><div class="t">${fmt(x)}</div><div class="d">${period(x.from, x.to)}</div></div>`).join('')}</div>`;
  };
  const withRole = x => `${esc(x.name)}${x.role ? `<div class="sub">${esc(x.role)}</div>` : ''}`;
  el.innerHTML = `
    <p class="explain">Stand der Stammdaten des Bundestages: ${esc(META.stammdaten.doc)}. Spätere Wechsel fehlen hier, bis der Bundestag die Stammdaten erneuert.</p>
    ${block('Ämter', C.offices, withRole)}
    ${block('Fraktion', C.fractions, withRole)}
    ${block('Ausschüsse', C.committees, withRole)}
    ${block('Weitere Gremien', C.other, withRole)}
    ${!C.offices.length && !C.fractions.length && !C.committees.length && !C.other.length ? '<div class="rows"><div class="empty">Keine Einträge in den Stammdaten.</div></div>' : ''}`;
}

function renderDocuments(el) {
  const only = el.dataset.only === '1';
  const row = d => `<div class="row"><div class="d">${shortDate(d.date)}</div>
    <div class="t">${esc(d.title)}<div class="sub">${[esc(d.activity === 'Frage' ? 'Schriftliche Frage' : d.activity), `Drs. ${esc(d.number)}`,
      d.activity !== 'Frage' && d.authors ? (d.authors === 1 ? 'allein gezeichnet' : `eine von ${n(d.authors)} Namen`) : '',
      d.subjects.length && esc(d.subjects.join(', '))].filter(Boolean).join(' · ')}</div></div>
    <div class="l">${d.pdf ? `<a href="${esc(d.pdf)}" title="${esc(d.cite)}">PDF</a>` : ''}</div></div>`;
  const docs = documents.filter(d => !only || (d.authors && d.authors <= SMALL_GROUP)).sort(byDateDesc);
  const small = documents.filter(d => d.authors && d.authors <= SMALL_GROUP).length;
  el.innerHTML = `
    <p class="explain">${dipSpan()}. Eine Drucksache zählt hier, wenn DIP diese Person als Urheber führt (Antrag, Kleine Anfrage, Entschließungs- und Änderungsantrag, Gesetzentwurf, schriftliche Frage). Fraktionsanträge tragen oft die Namen der ganzen Fraktion; die Zahl der Namen zeigt, ob eine Drucksache von wenigen oder von allen stammt.</p>
    ${META.dip.complete ? '' : '<p class="explain"><b>Noch unvollständig:</b> Die Drucksachen aus DIP werden gerade für die ganze Wahlperiode nachgeladen. Bis dahin fehlen Monate; deshalb nennt die Karte oben noch keine Zahlen.</p>'}
    <h2 id="drucksachen-eigene">Anträge, Anfragen, Gesetzentwürfe <span class="n">${n(docs.length)}</span></h2>
    ${documents.length ? `<div class="tools"><label><input type="checkbox"${only ? ' checked' : ''}> nur Drucksachen mit höchstens ${SMALL_GROUP} Namen (${n(small)})</label></div>` : ''}
    ${list(docs.map(row), 'Keine Drucksachen.')}
    ${writtenQuestions.length ? `<h2 id="drucksachen-fragen">Schriftliche Fragen <span class="n">${n(writtenQuestions.length)}</span></h2><p class="explain">Schriftliche Fragen erscheinen gesammelt in einer Drucksache je Woche; der Link führt zu dieser Sammlung.</p>${list(writtenQuestions.slice().sort(byDateDesc).map(row), '')}` : ''}
    ${C.reported.length ? `<h2 id="drucksachen-berichte">Berichterstattung <span class="n">${n(C.reported.length)}</span></h2><p class="explain">Als Berichterstatterin oder Berichterstatter eines Ausschusses auf einer Beschlussempfehlung genannt. Das ist eine Aufgabe im Ausschuss, keine Urheberschaft.</p>${list(C.reported.slice().sort(byDateDesc).map(row), '')}` : ''}`;
  el.querySelector('input')?.addEventListener('change', e => { el.dataset.only = e.target.checked ? '1' : ''; renderDocuments(el); });
}

function renderCareer(el) {
  const where = m => m.type === 'Direktwahl' ? `direkt gewählt im Wahlkreis ${m.number} · ${esc(m.constituency)}`
    : m.type === 'Landesliste' ? `Landesliste ${esc(stateName(m.state))}${m.number ? ` · Wahlkreiskandidatur in ${m.number} ${esc(m.constituency)}` : ''}`
    : m.type === 'Volkskammer' ? 'von der Volkskammer entsandt' : esc(m.type || '');
  const gaps = [];
  for (let i = 1; i < C.career.length; i++) if (C.career[i].wp - C.career[i - 1].wp > 1) gaps.push(`zwischen der ${C.career[i - 1].wp}. und der ${C.career[i].wp}. Wahlperiode`);
  const rows = C.career.slice().reverse().map(m => `<div class="row"><div class="t">${m.wp}. Wahlperiode<div class="sub">${m.wp === META.wp && C.election ? electionLine(C.election) + (C.election.via === 'constituency' && C.election.list_position ? `; abgesichert auf Platz ${C.election.list_position} der Landesliste ${STATES[C.election.list_state] || esc(C.election.list_state)}` : '') : where(m)}</div></div><div class="d">${period(m.from, m.to)}</div></div>`);
  el.innerHTML = `
    <p class="explain">Alle Mandate seit der ersten Wahlperiode laut Stammdaten des Bundestages (${esc(META.stammdaten.doc)}).</p>
    ${gaps.length ? `<p class="explain">Nicht im Bundestag ${gaps.join(', ')}.</p>` : ''}
    ${C.in_stammdaten ? '' : `<p class="explain">Das aktuelle Mandat fehlt in diesem Stand der Stammdaten; Mitglied spätestens seit ${longDate(C.first_vote)}.</p>`}
    <div class="rows memb">${rows.join('') || '<div class="empty">Keine Mandate in den Stammdaten.</div>'}</div>`;
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
      ${C.wikidata ? `<li>Wikidata: <a href="https://www.wikidata.org/wiki/${esc(C.wikidata)}">${esc(C.wikidata)}</a> (CC0 1.0)</li>` : ''}
      ${C.aw_id ? `<li>abgeordnetenwatch.de: <a href="https://www.abgeordnetenwatch.de/api/v2/politicians/${esc(C.aw_id)}">Datensatz ${esc(C.aw_id)}</a> (CC0 1.0)</li>` : ''}
      <li>Alle Angaben dieser Seite als <a href="${esc(C.id)}.json">JSON</a>.</li>
    </ul>
    <p class="explain">Die Daten werden mit <a href="https://github.com/jan-c-buchkremer/bundestag-data-foundation">bundestag-data-foundation</a> aus den Originalquellen gesammelt und täglich aktualisiert. Diese Seite wurde am ${shortDate(META.built)} erzeugt. Etwas stimmt nicht? <a href="${issue}">Fehler melden</a>.</p>`;
}

function renderTabs() {
  const want = (location.hash.slice(1) || 'reden');
  const active = TABS.find(t => want === t[0] || want.startsWith(t[0] + '-')) || TABS[0];
  document.getElementById('tabs').innerHTML = TABS.map(([id, label, count]) => {
    const k = count();
    return `<a href="#${id}" class="${id === active[0] ? 'on' : ''}">${label}${k !== '' ? `<span class="n">${n(k)}</span>` : ''}</a>`;
  }).join('');
  const body = document.getElementById('tabbody');
  if (body.dataset.tab !== active[0]) {
    body.dataset.tab = active[0];
    body.innerHTML = `<section class="tab on" id="tab-${active[0]}"></section>`;
    active[3](body.firstElementChild);
  }
  if (want !== active[0]) document.getElementById(want)?.scrollIntoView({ block: 'start' });
}

document.addEventListener('click', e => {
  const b = e.target.closest('.more');
  if (b) { document.getElementById(b.dataset.for).querySelectorAll('.row[hidden]').forEach(r => r.hidden = false); b.remove(); }
});
window.addEventListener('hashchange', () => {
  renderTabs();
  if (TABS.some(t => t[0] === location.hash.slice(1))) document.getElementById('tabs').scrollIntoView({ block: 'start' });
});

renderCard();
renderTabs();
document.getElementById('foot').innerHTML = `Daten: Deutscher Bundestag${member && META.election.length ? ', Die Bundeswahlleiterin' : ''}${C.aw_id ? ', abgeordnetenwatch.de (CC0 1.0)' : ''}. Code: <a href="${REPO}">bundestag-mdb-cards</a> (MIT). Keine Rangliste, keine Bewertung: Zahlen stehen immer mit ihrem Zusammenhang.`;
