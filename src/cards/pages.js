// The interactive parts of the vote and sitting pages (written as HTML by pages.py): the seating chart of a vote
// the filters of the votes overview and the long speech lists of a sitting. Reads PAGE. German UI, see docs/plan.md.
'use strict';

(function () {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const $ = id => document.getElementById(id);
  const n = x => x.toLocaleString('de-DE');
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const VOTE = { yes: 'Ja', no: 'Nein', abstain: 'Enthaltung', absent: 'nicht abgegeben', invalid: 'ungültig' };
  const POSITION = { yes: 'dafür', no: 'dagegen', abstain: 'Enthaltung' };
  const RANK = { yes: 0, no: 1, abstain: 2, invalid: 3, absent: 4 };
  const color = k => css(`--v-${k}`) || '#a1a1aa';
  const short = f => f === 'BÜNDNIS 90/DIE GRÜNEN' ? 'Grüne' : f;

  function legend(el, entries) {
    el.innerHTML = entries.filter(([, , c]) => c !== 0)
      .map(([k, label, c]) => `<span><i style="background:${color(k)}"></i>${esc(label)}${c != null ? ` <b>${n(c)}</b>` : ''}</span>`).join('');
  }

  // vote pages have no Regierungsbank or Bundesrat: drop that furniture and crop the chart to the seats
  function plenumOnly(chart) {
    const [furniture, seatsG] = chart.svg.children;
    furniture.remove();
    const b = seatsG.getBBox(), pad = 3;
    chart.svg.setAttribute('viewBox', [b.x - pad, b.y - pad, b.width + 2 * pad, b.height + 2 * pad].map(v => +v.toFixed(2)).join(' '));
  }

  function rollCall() {
    const tally = {};
    for (const [, , f, v] of PAGE.members) {
      tally[f] = tally[f] || { yes: 0, no: 0, abstain: 0 };
      if (v in tally[f]) tally[f][v]++;
    }
    const line = {};  // the fraction's majority (as the cards: none on a tie, none for fraktionslos)
    for (const [f, t] of Object.entries(tally)) {
      const r = Object.entries(t).sort((a, b) => b[1] - a[1]);
      line[f] = f !== 'fraktionslos' && r[0][1] > 0 && r[0][1] !== r[1][1] ? r[0][0] : null;
    }
    const seats = PAGE.members.map(([pid, name, fraction, vote], i) => ({
      id: pid || `row${i}`, pid, name, fraction, vote, group: String(RANK[vote] ?? 9), sort: name,
      deviates: !!line[fraction] && vote in POSITION && vote !== line[fraction],
    }));
    const chart = renderParliament($('chart'), seats, {
      colorOf: s => color(s.vote),
      tooltip: s => `<b>${esc(s.name)}</b><br><span class="sub">${esc(s.fraction)} · ${esc(VOTE[s.vote] || s.vote)}${s.deviates ? ' · anders als die Fraktionsmehrheit' : ''}</span>`,
      label: s => `${s.name}, ${s.fraction}: ${VOTE[s.vote] || s.vote}`,
      onClick: s => { if (s.pid) location.href = `../${encodeURIComponent(s.pid)}.html`; },
      government: [], bundesrat: 0, title: 'Stimmen im Plenum',
      tapHint: 'Nochmals tippen öffnet die Karte',
    });
    plenumOnly(chart);
    const count = k => seats.filter(s => s.vote === k).length;
    legend($('legend'), [['yes', 'Ja', count('yes')], ['no', 'Nein', count('no')], ['abstain', 'Enthaltung', count('abstain')], ['absent', 'nicht abgegeben', count('absent')], ['invalid', 'ungültig', count('invalid')]]);
    const dev = $('dev');
    const nDev = seats.filter(s => s.deviates).length;
    dev.parentNode.lastChild.textContent += ` (${n(nDev)})`;
    if (!nDev) dev.disabled = true;
    dev.onchange = () => chart.update({ dim: dev.checked ? s => !s.deviates : null, highlight: dev.checked ? s => s.deviates : null });
  }

  function hands() {
    const seats = [];
    for (const [f, k] of Object.entries(PAGE.house)) for (let i = 0; i < k; i++) seats.push({ id: `${f}#${i}`, fraction: f, name: f, sort: String(i).padStart(3, '0') });
    const pos = s => PAGE.positions[s.fraction] || 'unknown';
    const chart = renderParliament($('chart'), seats, {
      colorOf: s => color(pos(s)),
      tooltip: s => `<b>${esc(s.fraction)}</b><br><span class="sub">${esc(POSITION[pos(s)] || 'im Protokoll nicht genannt')}</span>`,
      label: s => `${s.fraction}: ${POSITION[pos(s)] || 'nicht genannt'}`,
      government: [], bundesrat: 0, title: 'Positionen der Fraktionen',
    });
    plenumOnly(chart);
    const by = {};
    for (const [f, p] of Object.entries(PAGE.positions)) (by[p] = by[p] || []).push(short(f));
    const missing = Object.keys(PAGE.house).filter(f => !PAGE.positions[f]).map(short);
    legend($('legend'), [
      ...['yes', 'no', 'abstain'].filter(k => by[k]).map(k => [k, `${POSITION[k]}: ${by[k].join(', ')}`, null]),
      ...(missing.length ? [['unknown', `nicht genannt: ${missing.join(', ')}`, null]] : []),
    ]);
  }

  function votes() {
    const q = $('q'), kind = $('kind'), result = $('result'), count = $('count');
    const rows = [...document.querySelectorAll('#groups .row')].map(el => ({ el, text: el.textContent.toLowerCase() }));
    const groups = [...document.querySelectorAll('#groups .grp')];
    const params = new URLSearchParams(location.hash.slice(1));
    q.value = params.get('q') || '';
    kind.value = params.get('art') || '';
    result.value = params.get('ergebnis') || '';
    function apply() {
      const terms = q.value.toLowerCase().split(/\s+/).filter(Boolean);
      let shown = 0;
      for (const r of rows) {
        const ok = (!kind.value || r.el.dataset.kind === kind.value) && (!result.value || r.el.dataset.result === result.value)
          && terms.every(t => r.text.includes(t));
        r.el.hidden = !ok;
        if (ok) shown++;
      }
      for (const g of groups) g.hidden = !g.querySelector('.row:not([hidden])');
      count.textContent = shown === rows.length ? `${n(rows.length)} Beschlüsse` : `${n(shown)} von ${n(rows.length)} Beschlüssen`;
      const h = new URLSearchParams();
      if (q.value) h.set('q', q.value);
      if (kind.value) h.set('art', kind.value);
      if (result.value) h.set('ergebnis', result.value);
      history.replaceState(null, '', h.size ? '#' + h : location.pathname);
    }
    q.oninput = kind.onchange = result.onchange = apply;
    apply();
  }

  // agenda items with many speeches: open and close the rest; closing keeps the button where it was on screen
  function sitting() {
    for (const box of document.querySelectorAll('.sp-list')) {
      const btn = box.querySelector('.sp-more');
      btn.onclick = () => {
        const open = !box.classList.contains('open'), before = btn.getBoundingClientRect().top;
        box.classList.toggle('open', open);
        btn.setAttribute('aria-expanded', String(open));
        btn.textContent = open ? 'weniger Reden zeigen' : `alle ${box.dataset.n} Reden zeigen`;
        if (!open) window.scrollBy(0, btn.getBoundingClientRect().top - before);
      };
    }
  }

  if (PAGE.kind === 'vote' && PAGE.members) rollCall();
  else if (PAGE.kind === 'vote' && PAGE.house) hands();
  else if (PAGE.kind === 'votes') votes();
  else if (PAGE.kind === 'sitting') sitting();
})();
