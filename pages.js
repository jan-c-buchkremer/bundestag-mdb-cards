// The interactive parts of the pages written as HTML by Python: the seating chart of every vote point (facts.py),
// the filters of the votes overview, the long speech lists of a sitting and the "Alle N zeigen" of fact lists.
// Reads PAGE. Also highlights the terms of a Pagefind search result link (search.js sets `highlightParam: 'hl'`) on
// whatever page they lead to, so this runs on every shell()-built page. German UI, see docs/plan.md.
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
  // the way back to the site root, from the stylesheet link every page has ("../cards.css" or "cards.css")
  const ROOT = (document.querySelector('link[href$="cards.css"]')?.getAttribute('href') || '').replace(/cards\.css$/, '');

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

  // one seating chart per vote (facts.py writes `.vchart` with the vote's data inside): every member's vote, the
  // fraction lines as computed in Python with data.majority (D22), or the fractions' positions by seats
  function rollCall(box, D) {
    const line = D.lines;
    const seats = D.members.map(([pid, name, fraction, vote], i) => ({
      id: pid || `row${i}`, pid, name, fraction, vote, group: String(RANK[vote] ?? 9), sort: name,
      deviates: !!line[fraction] && vote in POSITION && vote !== line[fraction],
    }));
    const chart = renderParliament(box.querySelector('.pm'), seats, {
      colorOf: s => color(s.vote),
      tooltip: s => `<b>${esc(s.name)}</b><br><span class="sub">${esc(s.fraction)} · ${esc(VOTE[s.vote] || s.vote)}${s.deviates ? ' · anders als die Fraktionsmehrheit' : ''}</span>`,
      label: s => `${s.name}, ${s.fraction}: ${VOTE[s.vote] || s.vote}`,
      onClick: s => { if (s.pid) location.href = `${ROOT}${encodeURIComponent(s.pid)}.html`; },
      government: [], bundesrat: 0, title: 'Stimmen im Plenum',
      tapHint: 'Nochmals tippen öffnet die Karte',
    });
    plenumOnly(chart);
    const count = k => seats.filter(s => s.vote === k).length;
    legend(box.querySelector('.legend'), [['yes', 'Ja', count('yes')], ['no', 'Nein', count('no')], ['abstain', 'Enthaltung', count('abstain')], ['absent', 'nicht abgegeben', count('absent')], ['invalid', 'ungültig', count('invalid')]]);
    const dev = box.querySelector('input.dev');
    const nDev = seats.filter(s => s.deviates).length;
    dev.parentNode.lastChild.textContent += ` (${n(nDev)})`;
    if (!nDev) dev.disabled = true;
    dev.onchange = () => chart.update({ dim: dev.checked ? s => !s.deviates : null, highlight: dev.checked ? s => s.deviates : null });
  }

  function hands(box, D) {
    const seats = [];
    for (const [f, k] of Object.entries(D.house)) for (let i = 0; i < k; i++) seats.push({ id: `${f}#${i}`, fraction: f, name: f, sort: String(i).padStart(3, '0') });
    const pos = s => D.positions[s.fraction] || 'unknown';
    const chart = renderParliament(box.querySelector('.pm'), seats, {
      colorOf: s => color(pos(s)),
      tooltip: s => `<b>${esc(s.fraction)}</b><br><span class="sub">${esc(POSITION[pos(s)] || 'im Protokoll nicht genannt')}</span>`,
      label: s => `${s.fraction}: ${POSITION[pos(s)] || 'nicht genannt'}`,
      government: [], bundesrat: 0, title: 'Positionen der Fraktionen',
    });
    plenumOnly(chart);
    const by = {};
    for (const [f, p] of Object.entries(D.positions)) (by[p] = by[p] || []).push(short(f));
    const missing = Object.keys(D.house).filter(f => !D.positions[f]).map(short);
    legend(box.querySelector('.legend'), [
      ...['yes', 'no', 'abstain'].filter(k => by[k]).map(k => [k, `${POSITION[k]}: ${by[k].join(', ')}`, null]),
      ...(missing.length ? [['unknown', `nicht genannt: ${missing.join(', ')}`, null]] : []),
    ]);
  }

  function charts() {
    if (typeof renderParliament !== 'function') return;
    for (const box of document.querySelectorAll('.vchart')) {
      const D = JSON.parse(box.querySelector('script[type="application/json"]').textContent);
      if (D.mode === 'rc') rollCall(box, D);
      else hands(box, D);
    }
  }

  function votes() {
    const q = $('q'), kind = $('kind'), result = $('result'), count = $('count');
    const rows = [...document.querySelectorAll('#groups .dec')].map(el => ({ el, text: el.textContent.toLowerCase() }));
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
      for (const g of groups) g.hidden = !g.querySelector('.dec:not([hidden])');
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

  // marks the terms of a search result link (?hl=wort, one per param, as pagefind's processedUrl appends them)
  // inside the page's indexed text and scrolls to the first hit; a no-op without a "hl" param or indexed text
  function highlightQuery() {
    const terms = [...new Set(new URLSearchParams(location.search).getAll('hl').map(t => t.trim()).filter(Boolean))];
    const root = document.querySelector('[data-pagefind-body]');
    if (!terms.length || !root) return;
    const pattern = terms.sort((a, b) => b.length - a.length)
      .map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|');
    const test = new RegExp(pattern, 'iu'), all = new RegExp(pattern, 'giu');
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: node => node.parentNode && !/^(SCRIPT|STYLE|MARK)$/.test(node.parentNode.tagName) && test.test(node.nodeValue)
        ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT,
    });
    const nodes = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node);
    let first = null;
    for (const textNode of nodes) {
      const text = textNode.nodeValue, frag = document.createDocumentFragment();
      let last = 0, m;
      while ((m = all.exec(text))) {
        if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
        const mark = document.createElement('mark');
        mark.textContent = m[0];
        frag.appendChild(mark);
        first ??= mark;
        last = m.index + m[0].length;
      }
      frag.appendChild(document.createTextNode(text.slice(last)));
      textNode.parentNode.replaceChild(frag, textNode);
    }
    if (first && typeof first.scrollIntoView === 'function') first.scrollIntoView({ block: 'center' });
  }

  // fact lists longer than their limit (facts.py): "Alle N zeigen" opens the rows cut off in that list
  document.addEventListener('click', e => {
    const b = e.target.closest('button.more[data-for]');
    if (!b) return;
    $(b.dataset.for).querySelectorAll('[data-cut]').forEach(r => { r.hidden = false; r.removeAttribute('data-cut'); });
    b.remove();
  });

  highlightQuery();
  charts();
  sitting();
  if (PAGE.kind === 'votes') votes();
})();
