// The search field at the left end of the top bar (ui.site_header, docs/plan.md 12.1). Without JavaScript it is a
// plain form: Enter goes to suche.html?q=…. With it, typing shows suggestions from suche-kurz.json (the entity
// index without the Gemeinden, search.py), grouped by type and ranked by search.js's resolve(), so the bar and the
// search page find the same entities in the same order. The index and search.js are fetched on the first keystroke,
// never on page load. On narrow screens the field is an icon that opens it over the bar.
'use strict';
(() => {
  const form = document.querySelector('header .nav-q');
  if (!form) return;
  const root = form.dataset.root || '';
  const input = form.querySelector('input');
  const box = form.querySelector('.nav-sug');
  const icon = form.querySelector('.nav-qi');
  const header = form.closest('header');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const narrow = matchMedia('(max-width: 1080px)');
  let index = null, loading = null, links = [], hi = -1;

  function lib() {
    if (window.cardsSearch) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.type = 'module';  // a module: its helpers do not collide with a page's own globals
      s.src = `${root}search.js`;
      s.onload = resolve;
      s.onerror = reject;
      document.head.append(s);
    });
  }

  function load() {
    loading ??= Promise.all([fetch(`${root}suche-kurz.json`).then(r => r.ok ? r.json() : null), lib()])
      .then(([idx]) => { index = idx; })
      .catch(() => { index = null; });
    return loading;
  }

  function close() { box.hidden = true; links = []; hi = -1; }

  function render() {
    const q = input.value.trim();
    if (q.length < 2 || !index || !window.cardsSearch) { close(); return; }
    const groups = window.cardsSearch.resolve(index, q, 4);
    const all = `<a class="all" href="${root}suche.html?q=${encodeURIComponent(q)}">Alle Treffer für „${esc(q)}“, auch in Reden →</a>`;
    box.innerHTML = groups.map(g => `<div class="g">${esc(g.type)}</div>` + g.items.map(x =>
      `<a href="${root}${esc(x.href)}">${esc(x.label)}<span class="s">${esc(x.sub)}</span></a>`).join('')).join('') + all;
    box.hidden = false;
    links = [...box.querySelectorAll('a')];
    hi = -1;
  }

  input.addEventListener('input', () => { if (input.value.trim().length >= 2) load().then(render); else close(); });
  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') { close(); if (narrow.matches) toggle(false); return; }
    if (box.hidden || !links.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      hi = Math.max(0, Math.min(links.length - 1, hi + (e.key === 'ArrowDown' ? 1 : -1)));
      links.forEach((a, i) => a.classList.toggle('hi', i === hi));
      links[hi].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter' && hi >= 0) {
      e.preventDefault();
      location.href = links[hi].href;
    }
  });
  form.addEventListener('submit', e => { if (!input.value.trim()) e.preventDefault(); });

  function toggle(open) {
    header.classList.toggle('q-open', open);
    icon.setAttribute('aria-expanded', open);
    if (open) input.focus(); else close();
  }
  icon.addEventListener('click', () => narrow.matches ? toggle(!header.classList.contains('q-open')) : input.focus());
  document.addEventListener('click', e => {
    if (form.contains(e.target)) return;
    close();
    if (narrow.matches && header.classList.contains('q-open')) toggle(false);
  });
})();
