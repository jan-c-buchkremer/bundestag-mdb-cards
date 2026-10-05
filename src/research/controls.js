// The visual controls of the Research pages (controls.py, docs/plan.md goal 3): every chart is also a filter. Python
// draws the charts and writes every row of the list; this module only filters. A page has one scope (.ctl-scope)
// with toggle buttons (data-f = the key, data-v = the value), a search field (data-q), "zurücksetzen" (data-reset),
// an activity strip (.strip, buttons per week with data-w) and the list (data-rows), whose rows carry their values as
// data attributes. Values of one key are alternatives, keys combine. The state lives in the URL fragment
// (#art=antrag&von=cdu,spd&zeit=2026-W10..2026-W20&q=miete&ansicht=stufe), so a view can be shared and the back
// button works; a fragment without "=" is an anchor and stays one. Each chart (figure.cv[data-view]) has a switch to
// its table, remembered as ansicht=<chart>. Without this script the page shows every chart, its table and the full
// list. German UI, see docs/plan.md. parse, serialize and matches are pure and run in Node (tests/test_controls.py).
//
// Also: a key whose buttons carry data-single holds one value and chooses what the list is (Fragen: the kind), it
// filters nothing and "zurücksetzen" keeps it; data-set="key=value" on a button also chooses that value when the
// button is switched on; the counts of buttons inside [data-static] stay as Python wrote them (a chart of another
// list). A page script whose list is loaded later (fragen.js) gets the scope's API from the "controls:change" event
// and hands it its rows with setRows(rows, render).
'use strict';

(function () {
  const WEEK = /^\d{4}-W\d{2}$/;
  const dec = s => { try { return decodeURIComponent(s.replace(/\+/g, ' ')); } catch { return ''; } };
  const enc = s => encodeURIComponent(s);

  function empty() {
    return { f: {}, zeit: null, q: '', ansicht: [] };
  }

  // the state of a URL fragment; a plain anchor (#glossar) is no state
  function parse(hash) {
    const state = empty();
    const h = String(hash || '').replace(/^#/, '');
    if (!h.includes('=')) return state;
    for (const part of h.split('&')) {
      const i = part.indexOf('=');
      if (i < 1) continue;
      const k = dec(part.slice(0, i)), raw = part.slice(i + 1);
      if (k === 'q') state.q = dec(raw);
      else if (k === 'zeit') {
        const [a, b = a] = raw.split('..').map(dec);
        if (WEEK.test(a) && WEEK.test(b)) state.zeit = a <= b ? [a, b] : [b, a];
      } else {
        const vals = [...new Set(raw.split(',').map(dec).filter(Boolean))];
        if (k === 'ansicht') state.ansicht = vals;
        else if (vals.length) state.f[k] = vals;
      }
    }
    return state;
  }

  // the fragment of a state, without "#"; keys in a fixed order, so one view has one URL
  function serialize(state) {
    const parts = [];
    for (const k of Object.keys(state.f).sort()) {
      if (state.f[k].length) parts.push(`${enc(k)}=${state.f[k].map(enc).join(',')}`);
    }
    if (state.zeit) parts.push(`zeit=${state.zeit[0] === state.zeit[1] ? state.zeit[0] : state.zeit.join('..')}`);
    if (state.q) parts.push(`q=${enc(state.q)}`);
    if (state.ansicht.length) parts.push(`ansicht=${state.ansicht.map(enc).join(',')}`);
    return parts.join('&');
  }

  // whether a row ({tok: {key: [values]}, w: ISO week, text: lower-case text}) passes every filter but `skip`;
  // `singles`: the keys that choose the list rather than filter it
  function matches(row, state, skip, singles) {
    for (const [k, vals] of Object.entries(state.f)) {
      if (k === skip || !vals.length || singles?.has(k)) continue;
      const have = row.tok[k] || [];
      if (!vals.some(v => have.includes(v))) return false;
    }
    if (skip !== 'zeit' && state.zeit && !(row.w && row.w >= state.zeit[0] && row.w <= state.zeit[1])) return false;
    if (skip !== 'q' && state.q) {
      const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
      if (!words.every(w => row.text.includes(w))) return false;
    }
    return true;
  }

  function active(state, singles) {
    return Object.entries(state.f).some(([k, v]) => v.length && !singles?.has(k)) || !!state.zeit || !!state.q;
  }

  // ---------------------------------------------------------------- the page

  function mount() {
    const n = x => x.toLocaleString('de-DE');
    const scope = document.querySelector('.ctl-scope');
    const views = [...document.querySelectorAll('figure.cv[data-view]')];
    const toggles = scope ? [...scope.querySelectorAll('[data-f][data-v]')] : [];
    const keys = [...new Set(toggles.map(b => b.dataset.f))];
    const singles = new Set(toggles.filter(b => 'single' in b.dataset).map(b => b.dataset.f));
    const values = Object.fromEntries(keys.map(k => [k, new Set(toggles.filter(b => b.dataset.f === k).map(b => b.dataset.v))]));
    const list = scope?.querySelector('[data-rows]');
    const attr = k => scope.getAttribute(`data-attr-${k}`) || k;
    let rows = list && !('external' in list.dataset) ? [...list.querySelectorAll(list.dataset.row || ':scope > .row')].map(el => ({
      el,
      tok: Object.fromEntries(keys.map(k => [k, (el.getAttribute(`data-${attr(k)}`) || '').split(' ').filter(Boolean)])),
      w: el.dataset.w || '',
      text: el.textContent.toLowerCase(),
    })) : [];
    let render = null;  // a page script's list (setRows); null: the rows are elements in the page
    let loaded = !list || !('external' in list.dataset);
    const groups = list ? [...list.querySelectorAll('[data-group]')] : [];
    const q = scope?.querySelector('[data-q]');
    const reset = scope?.querySelector('[data-reset]');
    const summary = scope?.querySelector('[data-summary]');
    const count = scope?.querySelector('[data-count]');
    const more = scope?.querySelector('[data-more]');
    const none = scope?.querySelector('[data-none]');
    const strip = scope?.querySelector('.strip');
    const bars = strip ? [...strip.querySelectorAll('.swk')] : [];
    const step = +(list?.dataset.limit || 30);
    const noun = scope?.dataset.noun || '', one = scope?.dataset.one || '', dat = scope?.dataset.dat || noun;
    let state = clean(parse(location.hash));
    let limit = step;
    let drag = null;  // the week a drag on the strip started at, and where it is now

    // only what the page has: an old or shared URL may name a value or key that is not here
    function clean(s) {
      for (const k of Object.keys(s.f)) {
        s.f[k] = s.f[k].filter(v => values[k]?.has(v));
        if (singles.has(k)) s.f[k] = s.f[k].slice(0, 1);
        if (!s.f[k].length) delete s.f[k];
      }
      if (s.zeit && !bars.length) s.zeit = null;
      return s;
    }

    // drop the values whose buttons are all in a hidden part of the page (another kind's filters)
    function prune() {
      for (const k of Object.keys(state.f)) {
        if (singles.has(k)) continue;
        state.f[k] = state.f[k].filter(v => toggles.some(b => b.dataset.f === k && b.dataset.v === v && !b.closest('[hidden]')));
        if (!state.f[k].length) delete state.f[k];
      }
    }

    function label(k, v) {
      const b = toggles.find(x => x.dataset.f === k && x.dataset.v === v && x.dataset.label);
      return b ? b.dataset.label : v;
    }

    function weekLabel(w) {
      const b = bars.find(x => x.dataset.w === w);
      return b ? b.dataset.label.replace(/, Sitzungswoche$/, '') : w;
    }

    function range(z) {
      return z[0] === z[1] ? weekLabel(z[0]) : `${weekLabel(z[0])} bis ${weekLabel(z[1])}`;
    }

    function commit(push) {
      const h = serialize(state);
      const url = h ? `#${h}` : location.pathname + location.search;
      if (url === (location.hash || location.pathname + location.search)) return;
      if (push) history.pushState(null, '', url);
      else history.replaceState(null, '', url);
    }

    function counts(z) {
      // per key and value: the rows that pass every other filter and carry the value
      if (loaded) {
        for (const k of keys) {
          if (singles.has(k)) continue;
          const c = {};
          for (const r of rows) if (matches(r, state, k, singles)) for (const v of r.tok[k] || []) c[v] = (c[v] || 0) + 1;
          for (const b of toggles) {
            if (b.dataset.f !== k || b.closest('[data-static]')) continue;
            const span = b.querySelector('.c');
            if (!span) continue;
            const all = +span.dataset.n, got = c[b.dataset.v] || 0;
            span.textContent = got === all ? n(all) : `${n(got)} von ${n(all)}`;
            b.classList.toggle('none', !got && !b.disabled);
          }
        }
      }
      if (!bars.length) return;
      const per = {};
      for (const r of rows) if (r.w && matches(r, state, 'zeit', singles)) per[r.w] = (per[r.w] || 0) + 1;
      const most = Math.max(1, ...bars.map(b => per[b.dataset.w] || 0));
      for (const b of bars) {
        const k = per[b.dataset.w] || 0, w = b.dataset.w;
        if (loaded) {
          b.firstElementChild.style.height = `${(100 * k / most).toFixed(1)}%`;
          b.setAttribute('aria-label', `${b.dataset.label}: ${n(k)} ${k === 1 ? one : noun}`);
        }
        b.setAttribute('aria-pressed', String(!!z && w >= z[0] && w <= z[1]));
      }
    }

    function apply() {
      for (const v of views) {
        const alt = state.ansicht.includes(v.dataset.view);
        v.classList.toggle('alt', alt);
        for (const b of v.querySelectorAll('[data-show]')) b.setAttribute('aria-pressed', String((b.dataset.show === 'alt') === alt));
      }
      if (!scope) return;
      for (const b of toggles) b.setAttribute('aria-pressed', String(!!state.f[b.dataset.f]?.includes(b.dataset.v)));
      if (q && q.value !== state.q) q.value = state.q;
      let hits = 0;
      const shownRows = [];
      for (const r of rows) {
        const ok = matches(r, state, undefined, singles);
        if (ok && hits < limit) shownRows.push(r);
        if (r.el) r.el.hidden = !ok || hits >= limit;
        if (ok) hits++;
      }
      if (render) render(shownRows);
      for (const g of groups) g.hidden = !g.querySelector(`${list.dataset.row || '.row'}:not([hidden])`);
      const shown = Math.min(hits, limit);
      if (more) {
        more.hidden = !loaded || hits <= limit;
        more.textContent = `mehr anzeigen (noch ${n(hits - limit)})`;
      }
      if (none) none.hidden = !loaded || hits > 0;
      if (count) {
        const base = hits === rows.length ? `${n(rows.length)} ${rows.length === 1 ? one : noun}` : `${n(hits)} von ${n(rows.length)} ${dat}`;
        count.textContent = !loaded ? '' : hits > shown ? `${base}, die neuesten ${n(shown)} hier` : base;
      }
      counts(drag ? [drag[0], drag[1]].sort() : state.zeit);
      const out = strip?.querySelector('[data-range]');
      if (out) out.textContent = state.zeit ? `${range(state.zeit)}: ${n(hits)} ${hits === 1 ? one : noun}` : 'Ganzer Zeitraum';
      const zx = strip?.querySelector('[data-zeit-clear]');
      if (zx) zx.hidden = !state.zeit;
      const parts = [];
      for (const k of keys) if (state.f[k] && !singles.has(k)) parts.push(state.f[k].map(v => label(k, v)).join(' oder '));
      if (state.zeit) parts.push(range(state.zeit));
      if (state.q) parts.push(`„${state.q}“`);
      if (summary) summary.textContent = parts.length ? `Auswahl: ${parts.join(' · ')}` : '';
      if (reset) reset.disabled = !active(state, singles);
      scope.dispatchEvent(new CustomEvent('controls:change', { detail: { state, api } }));
    }

    function change(fn, push = true) {
      fn();
      limit = step;
      apply();
      commit(push);
    }

    const api = {
      // the rows of a list a page script loaded: [{tok, w, text, ...}], drawn by render(rows shown)
      setRows(list_, draw) {
        rows = list_;
        render = draw;
        loaded = true;
        limit = step;
        prune();
        apply();
        commit(false);
      },
      // a list is being loaded: nothing to count yet
      unload() {
        rows = [];
        loaded = false;
        apply();
      },
      state: () => state,
    };
    if (scope) scope.controls = api;

    function setZeit(a, b) {
      const z = [a, b].sort();
      change(() => {
        const same = state.zeit && state.zeit[0] === z[0] && state.zeit[1] === z[1];
        state.zeit = same && a === b ? null : z;
      });
    }

    document.addEventListener('click', e => {
      const t = e.target.closest('[data-f][data-v], [data-show], [data-reset], [data-more], [data-zeit-clear], .swk');
      if (!t) return;
      if (t.matches('[data-show]')) {
        const key = t.closest('figure.cv').dataset.view;
        change(() => {
          state.ansicht = state.ansicht.filter(x => x !== key).concat(t.dataset.show === 'alt' ? [key] : []);
        });
      } else if (!scope || !scope.contains(t)) {
        return;
      } else if (t.matches('[data-f][data-v]')) {
        const { f, v } = t.dataset;
        change(() => {
          const cur = state.f[f] || [];
          const on = !cur.includes(v);
          if (singles.has(f)) state.f[f] = [v];
          else state.f[f] = on ? cur.concat(v) : cur.filter(x => x !== v);
          if (!state.f[f].length) delete state.f[f];
          if (on && t.dataset.set) {
            for (const pair of t.dataset.set.split(';')) {
              const [k, val] = pair.split('=');
              if (k && val) state.f[k] = [val];
            }
          }
        });
      } else if (t.matches('[data-reset]')) {
        change(() => {
          const kept = Object.fromEntries(Object.entries(state.f).filter(([k]) => singles.has(k)));
          state = { ...empty(), f: kept, ansicht: state.ansicht };
        });
        q?.focus();
      } else if (t.matches('[data-zeit-clear]')) {
        change(() => { state.zeit = null; });
      } else if (t.matches('[data-more]')) {
        limit += step;
        apply();
      } else if (t.matches('.swk') && e.detail === 0) {  // Enter or Space; a pointer is handled on pointerup
        setZeit(t.dataset.w, t.dataset.w);
      }
    });

    q?.addEventListener('input', () => change(() => { state.q = q.value.trim(); }, false));

    // the strip: press on a bar and drag across others for a range; arrow keys move, Shift + arrow widens
    if (strip) {
      const box = strip.querySelector('.strip-bars');
      const at = e => document.elementFromPoint(e.clientX, e.clientY)?.closest('.swk');
      box.addEventListener('pointerdown', e => {
        const b = e.target.closest('.swk');
        if (!b || e.button > 0) return;
        drag = [b.dataset.w, b.dataset.w];
        for (const x of bars) x.tabIndex = x === b ? 0 : -1;
        counts(drag.slice().sort());
      });
      box.addEventListener('pointermove', e => {
        if (!drag) return;
        const b = at(e);
        if (b && b.dataset.w !== drag[1]) {
          drag[1] = b.dataset.w;
          counts(drag.slice().sort());
        }
      });
      window.addEventListener('pointerup', () => {
        if (!drag) return;
        const [a, b] = drag;
        drag = null;
        setZeit(a, b);
      });
      window.addEventListener('pointercancel', () => { drag = null; apply(); });
      let anchor = null;
      box.addEventListener('keydown', e => {
        const b = e.target.closest('.swk');
        if (!b) return;
        const i = bars.indexOf(b);
        const j = { ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: bars.length - 1 }[e.key];
        if (j === undefined) return;
        e.preventDefault();
        const next = bars[Math.max(0, Math.min(bars.length - 1, j))];
        for (const x of bars) x.tabIndex = x === next ? 0 : -1;
        next.focus();
        if (e.shiftKey) {
          anchor = anchor || b.dataset.w;
          change(() => { state.zeit = [anchor, next.dataset.w].sort(); });
        } else {
          anchor = null;
        }
      });
    }

    function reread() {
      // the back and forward buttons, or a URL typed by hand; an anchor only scrolls and keeps the filters
      if (location.hash && !location.hash.includes('=')) return;
      state = clean(parse(location.hash));
      limit = step;
      apply();
    }
    window.addEventListener('popstate', reread);
    window.addEventListener('hashchange', reread);

    apply();
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { parse, serialize, matches, empty };
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
  else mount();
})();
