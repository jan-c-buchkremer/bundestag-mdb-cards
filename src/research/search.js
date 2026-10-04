// Custom search UI for suche.html (search.py writes the markup, this fills it): entity resolution first, from the
// suche.json the build writes (docs/plan.md 11.7, D20), then full-text hits in speeches from the Pagefind JS API.
// German UI, see docs/plan.md. Pure, DOM-free helpers are exported at the bottom for tests; everything else only
// runs in a browser with a #search element, so requiring this file in Node is side-effect-free.
'use strict';

const PAGE_SIZE = 10;
const CAP = 8; // filter values shown before "N weitere"
const GROUPS = ['Art', 'Fraktion', 'Thema', 'Monat', 'Person'];
const LABELS = { Art: 'Art', Fraktion: 'Fraktion', Thema: 'Thema', Monat: 'Monat', Person: 'Person' };

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

// Pagefind excerpts are plain text with the matches already wrapped in <mark>…</mark>: escape everything else,
// keep the marks (dropped tags stay html-safe either way).
function markSafe(html) {
  return String(html ?? '').split(/(<mark>.*?<\/mark>)/gs)
    .map(part => part.startsWith('<mark>') ? `<mark>${esc(part.slice(6, -7))}</mark>` : esc(part)).join('');
}

// ------------------------------------------------------------------ entities

const ENTITY_CAP = 6; // entities shown per type before "N weitere"

// lower case, no diacritics, "ß" as "ss": "Thüringen" and "thuringen" meet, as do "Straße" and "strasse"
function norm(s) {
  return String(s ?? '').toLowerCase().replace(/ß/g, 'ss').normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

// The entities matching every word of the query, grouped by type in the index's order, each group best first: the
// label equal to the query, then starting with it, then with a word starting with it, then any match (ties keep the
// index's order). index is suche.json: {types, items: [[type, label, sub, href, keys], …]}.
function resolve(index, q, cap = ENTITY_CAP) {
  const words = norm(q).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const query = words.join(' ');
  const groups = index.types.map(type => ({ type, total: 0, items: [] }));
  index.items.forEach(([t, label, sub, href, keys], i) => {
    const l = norm(label), hay = `${l} ${norm(sub)} ${norm(keys)}`;
    if (!words.every(w => hay.includes(w))) return;
    const rank = l === query ? 0 : l.startsWith(query) ? 1 : words.every(w => (' ' + l).includes(' ' + w)) ? 2 : 3;
    groups[t].items.push({ label, sub, href, rank, i });
  });
  for (const g of groups) {
    g.items.sort((a, b) => a.rank - b.rank || a.i - b.i);
    g.total = g.items.length;
    g.items = g.items.slice(0, cap).map(({ label, sub, href }) => ({ label, sub, href }));
  }
  return groups.filter(g => g.total);
}

function entitiesHtml(groups) {
  return groups.map(g => `<section class="s-ent"><h3>${esc(g.type)} <span class="n">${g.total}</span></h3>` +
    `<div class="rows">${g.items.map(x => `<a class="row sent" href="${esc(x.href)}"><span class="t">` +
      `<span class="ti">${esc(x.label)}</span><span class="sub">${esc(x.sub)}</span></span></a>`).join('')}</div>` +
    (g.total > g.items.length ? `<p class="faint">und ${g.total - g.items.length} weitere – genauer suchen</p>` : '') +
    '</section>').join('');
}

// ------------------------------------------------------------------ speeches (Pagefind)

function formatDate(iso) {
  return iso && iso.length >= 10 ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : '';
}

// One result row, styled like the rest of the site's .rows/.row (votes, sittings): `d` is what result.data() gives.
function resultRow(d) {
  const art = d.filters?.Art?.[0] || '';
  const date = formatDate(d.meta?.date);
  const title = esc(d.meta?.title || d.url);
  return `<a class="row sres" href="${esc(d.url)}"><span class="d">${esc(date)}</span>` +
    `<span class="t"><span class="ti">${title}</span><span class="sub">${markSafe(d.excerpt)}</span></span>` +
    `<span class="l">${art ? `<span class="tag">${esc(art)}</span>` : ''}</span></a>`;
}

// The query string for a deep link: ?q=… plus one entry per checked filter value ("OR within a group" mirrors
// the search itself). checked is {group: Set<string>}.
function queryString(q, checked) {
  const h = new URLSearchParams();
  if (q) h.set('q', q);
  for (const g of GROUPS) for (const v of checked[g] || []) h.append(g, v);
  return h.toString();
}

// The values of one filter group, sorted by their live count descending (ties alphabetically): `total` is the
// group's full value set (from pagefind.filters(), so a value can be listed even at zero), `live` the counts for
// the current query and the other active filters (from a search result's `filters`).
function sortValues(total, live) {
  return Object.keys(total).sort((a, b) => (live[b] || 0) - (live[a] || 0) || a.localeCompare(b, 'de'));
}

// The HTML of one filter group panel.
function filterGroupHtml(group, total, live, checked, open) {
  const values = sortValues(total, live || {});
  const shown = open ? values : values.slice(0, CAP);
  const rows = shown.map(v => {
    const c = (live || {})[v] || 0, on = checked.has(v);
    return `<label class="sf-item${!c && !on ? ' zero' : ''}"><input type="checkbox" data-g="${esc(group)}" ` +
      `value="${esc(v)}"${on ? ' checked' : ''}><span class="sf-name">${esc(v)}</span><span class="sf-n">${c}</span></label>`;
  }).join('');
  const more = values.length > CAP
    ? `<button type="button" class="sf-more" data-g="${esc(group)}">${open ? 'weniger' : `${values.length - CAP} weitere`}</button>`
    : '';
  return `<div class="sf-group"><h3>${esc(LABELS[group] || group)}</h3>` +
    `<div class="sf-list${open ? ' expanded' : ''}">${rows}</div>${more}</div>`;
}

async function boot() {
  const $ = id => document.getElementById(id);
  const n = x => x.toLocaleString('de-DE');
  const els = {
    input: $('sq'), toggle: $('sf-toggle'), filters: $('sf-panel'), count: $('s-count'),
    results: $('s-results'), more: $('s-more'), entities: $('s-entities'),
  };
  let INDEX = null;
  const renderEntities = () => {
    if (!INDEX) return;
    const groups = resolve(INDEX, els.input.value);
    els.entities.innerHTML = groups.length ? entitiesHtml(groups)
      : (els.input.value.trim() ? '<p class="empty">Keine Person, kein Ort, Gremium, Vorgang, Thema oder keine Woche mit diesem Namen.</p>' : '');
  };
  const entitiesReady = fetch('suche.json').then(r => r.json()).then(x => { INDEX = x; renderEntities(); })
    .catch(() => { els.entities.innerHTML = ''; });

  const state = { checked: {}, open: {}, master: {}, results: [], shown: 0 };

  function activeFilters() {
    const f = {};
    for (const g of GROUPS) if (state.checked[g]?.size) f[g] = [...state.checked[g]];
    return f;
  }

  function syncUrl() {
    const qs = queryString(els.input.value, state.checked);
    history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
  }

  function renderFilters(live) {
    els.filters.innerHTML = GROUPS.filter(g => state.master[g])
      .map(g => filterGroupHtml(g, state.master[g], live?.[g], state.checked[g] || new Set(), !!state.open[g]))
      .join('');
    els.filters.querySelectorAll('input[type=checkbox]').forEach(cb => {
      cb.onchange = () => {
        const g = cb.dataset.g;
        const set = state.checked[g] || (state.checked[g] = new Set());
        set[cb.checked ? 'add' : 'delete'](cb.value);
        run(false);
      };
    });
    els.filters.querySelectorAll('.sf-more').forEach(btn => {
      btn.onclick = () => { state.open[btn.dataset.g] = !state.open[btn.dataset.g]; renderFilters(live); };
    });
  }

  async function renderResults() {
    const slice = state.results.slice(0, state.shown);
    const data = slice.length ? await Promise.all(slice.map(r => r.data())) : [];
    els.results.innerHTML = data.length ? data.map(resultRow).join('') : '<p class="empty">Keine Treffer.</p>';
    els.more.hidden = state.shown >= state.results.length;
  }

  async function run(debounced) {
    const q = els.input.value.trim();
    const opts = { filters: activeFilters() };
    const res = debounced ? await pagefind.debouncedSearch(q || null, opts, 200) : await pagefind.search(q || null, opts);
    if (res === null) return; // superseded by a newer keystroke
    state.results = res.results;
    state.shown = Math.min(PAGE_SIZE, state.results.length);
    els.count.textContent = state.results.length
      ? (q ? `${n(state.results.length)} Treffer für „${q}“` : `${n(state.results.length)} Treffer`)
      : (q ? `Keine Treffer für „${q}“` : 'Keine Treffer');
    renderFilters(res.filters);
    await renderResults();
    syncUrl();
  }

  els.input.oninput = () => { renderEntities(); run(true); };
  els.more.onclick = () => { state.shown = Math.min(state.shown + PAGE_SIZE, state.results.length); renderResults(); };
  if (els.toggle) {
    els.toggle.onclick = () => {
      const open = els.filters.classList.toggle('open');
      els.toggle.setAttribute('aria-expanded', String(open));
    };
  }

  const params = new URLSearchParams(location.search);
  els.input.value = params.get('q') || '';
  for (const g of GROUPS) {
    const vs = params.getAll(g);
    if (vs.length) state.checked[g] = new Set(vs);
  }

  await entitiesReady;
  const pagefind = await import('./pagefind/pagefind.js');
  await pagefind.options({ highlightParam: 'hl' });
  state.master = await pagefind.filters();
  window.pagefind = pagefind; // for debugging in the console only

  // idle state (no query, no filter checked): show the filters with their site-wide counts, but skip an expensive
  // unfiltered "browse everything" search until the visitor actually asks for one
  if (els.input.value || Object.values(state.checked).some(s => s.size)) {
    await run(false);
  } else {
    renderFilters(state.master);
    els.results.innerHTML = '<p class="empty">Reden erscheinen, sobald du suchst oder einen Filter wählst.</p>';
  }
}

if (typeof document !== 'undefined' && document.getElementById('search')) {
  boot();
}

// the top bar's search field (nav.js) ranks its suggestions with the same resolve()
if (typeof window !== 'undefined') window.cardsSearch = { resolve, norm };

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { esc, markSafe, formatDate, resultRow, queryString, sortValues, filterGroupHtml, norm, resolve,
    entitiesHtml };
}
