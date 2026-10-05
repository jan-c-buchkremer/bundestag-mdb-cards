// The front page (landing.py): the house as it sits today, every seat a link to its card (parliament.js).
'use strict';
(function () {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const TOK = PAGE.token;
  const seats = PAGE.seats.map(s => ({ id: s.id, fraction: s.fraction, name: s.name, lead: s.lead, group: s.state || '', sort: s.last + ' ' + s.name, row: s }));
  renderParliament(document.getElementById('chart'), seats, {
    title: `Sitzverteilung im 21. Bundestag, ${seats.length} Sitze`,
    colorOf: s => css('--' + (TOK[s.fraction] || 'frl')),
    tooltip: s => `${s.row.photo ? `<img class="av tip-av" src="fotos/${encodeURIComponent(s.id)}.jpg" alt="" style="float:left;width:38px;height:50px;margin:1px 9px 2px 0;border-radius:5px;object-fit:cover">` : ''}<b>${esc(s.name)}</b><div class="sub">${esc(s.fraction)}</div>${s.row.office ? `<div>${esc(s.row.office)}</div>` : ''}`,
    tapHint: 'Nochmals tippen öffnet den Steckbrief',
    onClick: s => { location.href = `${encodeURIComponent(s.id)}.html`; },
  });
})();
