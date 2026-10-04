// Places in the browser (docs/plan.md 12.2, D25). Who represents a place is computed once, in places.py
// (`membership`), and shipped with the pages; this file never decides membership itself, it only expands the
// references the payload uses to avoid repeating a Land's list on each of its Wahlkreise. The place search runs over
// one index, orte/orte.json (places.py `place_index`), on the Orte page and in the Abgeordnete page's place filter
// alike. Pure helpers; exported for the tests in Node, `window.Places` in the browser.
'use strict';

(function (global) {
  // lower case, no diacritics, "ß" as "ss", as search.js
  function norm(s) {
    return String(s ?? '').toLowerCase().replace(/ß/g, 'ss').normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  // The members of a place: members[key] is a list of person ids and "@<key>" references (a Wahlkreis refers to
  // its Land's list members). Returns the ids in page order, each once; an unknown key gives [].
  function expand(members, key, seen = new Set()) {
    const out = [];
    if (seen.has(key)) return out;
    seen.add(key);
    for (const x of members[key] || []) {
      if (typeof x === 'string' && x.startsWith('@')) out.push(...expand(members, x.slice(1), seen));
      else out.push(x);
    }
    return [...new Set(out)];
  }

  const landHref = slug => `orte/${slug}.html`;
  const wkHref = nr => `orte/wahlkreis-${nr}.html`;

  // Places matching every word of the query: Länder, then Wahlkreise (by name or number), then Gemeinden (each
  // leading to its Wahlkreis; a Gemeinde split across Wahlkreise gives one result per part). Within a kind: the
  // label equal to the query first, then starting with it, then the rest in index order. index is orte/orte.json:
  // {lands: [[code, name, slug]], wahlkreise: [[nr, name, land]], gemeinden: [[name, district, land, [nr, …]]]}.
  // Every result carries `key` (the filter key: a Land code or a Wahlkreis number) and `href` (its place page,
  // relative to the site root).
  function search(index, q, cap = 12) {
    const words = norm(q).split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    const query = words.join(' ');
    const lands = Object.fromEntries((index.lands || []).map(([code, name, slug]) => [code, { name, slug }]));
    const wks = Object.fromEntries((index.wahlkreise || []).map(([nr, name, land]) => [nr, { name, land }]));
    const out = [];
    const add = (rank, k, i, x) => out.push({ ...x, rank, k, i });
    const rankOf = (label, hay) => {
      if (!words.every(w => hay.includes(w))) return -1;
      const l = norm(label);
      return l === query ? 0 : l.startsWith(query) ? 1 : 2;
    };
    (index.lands || []).forEach(([code, name, slug], i) => {
      const r = rankOf(name, norm(`${name} ${code}`));
      if (r >= 0) add(r, 0, i, { kind: 'land', key: code, label: name, sub: 'Land', href: landHref(slug) });
    });
    (index.wahlkreise || []).forEach(([nr, name, land], i) => {
      const exact = words.length === 1 && words[0] === String(nr);
      const r = exact ? 0 : rankOf(name, norm(`${name} ${nr} wahlkreis`));
      if (r >= 0) add(r, 1, i, { kind: 'wk', key: String(nr), label: `Wahlkreis ${nr}: ${name}`, sub: lands[land]?.name || '', href: wkHref(nr) });
    });
    (index.gemeinden || []).forEach(([name, district, land, nrs], i) => {
      const r = rankOf(name, norm(`${name} ${district}`));
      if (r < 0) return;
      for (const nr of nrs) {
        add(r, 2, i, {
          kind: 'gemeinde', key: String(nr), label: `${name}${nrs.length > 1 ? ' (Teil)' : ''}`,
          sub: `${district !== name ? district + ', ' : ''}${lands[land]?.name || land} · Wahlkreis ${nr}${wks[nr] ? ': ' + wks[nr].name : ''}`,
          href: wkHref(nr),
        });
      }
    });
    out.sort((a, b) => a.k - b.k || a.rank - b.rank || a.i - b.i);
    return out.slice(0, cap).map(({ rank, k, i, ...x }) => x);
  }

  // An old view state of the Abgeordnete page that moved to the place pages (docs/plan.md 12.6): "#ansicht=wahlkreise"
  // with "wk=<nr>" or "state=<Land>", relative to the site root; null for every other hash. `slugs` maps Land codes
  // to their page slugs.
  function legacyTarget(hash, slugs) {
    const h = new URLSearchParams(String(hash || '').replace(/^#/, ''));
    if (h.get('ansicht') !== 'wahlkreise') return null;
    const wk = parseInt(h.get('wk'), 10);
    if (wk > 0) return wkHref(wk);
    const st = h.get('state');
    if (st && slugs[st]) return landHref(slugs[st]);
    return 'orte/index.html';
  }

  const api = { norm, expand, search, legacyTarget };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else global.Places = api;
})(typeof window !== 'undefined' ? window : globalThis);
