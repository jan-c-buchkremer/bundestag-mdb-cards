/* Seating chart of the Bundestag as an SVG hemicycle, after the Sitzverteilung graphic on bundestag.de.
 *
 *   const chart = renderParliament(el, seats, options)
 *
 * seats: one object per member, drawn in the fraction wedges. Read fields:
 *   id        unique string (also used by highlight/dim sets)
 *   fraction  wedge key; wedges go in PARLIAMENT_ORDER (seen from the Präsidium: AfD left … Die Linke right),
 *             unknown fractions before "fraktionslos"
 *   name      shown in the default tooltip and aria-label
 *   lead      optional number, fraction leadership rank (lower = more senior): these sit in the front row
 *   group     optional sort group inside a wedge after leadership, e.g. the Land (then `sort`, then `name`)
 *   sort      optional sort key inside a group (default `name`)
 * Any other fields are passed through to the callbacks untouched.
 *
 * options (all optional):
 *   colorOf(seat)        CSS colour of a seat; default: the fraction colour from the page's --cdu/--spd/… tokens
 *   onClick(seat, event) activation: mouse click, Enter/Space, or the second tap on the same seat on touch
 *   tooltip(seat)        HTML of the tooltip (trusted, escape your own text); default: name, fraction
 *   label(seat)          aria-label text; default: name, fraction
 *   highlight            Set of ids, or a function seat => bool: drawn with a thin halo (pass dim for the rest)
 *   dim                  Set of ids, or a function seat => bool: faded to 25 %
 *   government           seats on the Regierungsbank (top left), in the given order
 *   presidium            seats in the Präsidium (top centre); the first is the chair
 *   bundesrat            number of empty Bundesrat seats (top right), default: as many as the Regierungsbank has
 *   order                fraction order, default PARLIAMENT_ORDER
 *   title                accessible name of the chart, default "Sitzverteilung im Bundestag"
 *   emptyTips            tooltip HTML of the seats without a person, by block: { regierung, bundesrat, praesidium,
 *                        stenografen }; defaults in EMPTY_TIPS ("Bundesrat – nicht Teil dieses Datensatzes", …)
 *   tapHint              line added to the tooltip after a first tap, default "Nochmals tippen zum Öffnen"
 *
 * Returns { svg, update(options), seat(id), destroy() }. update() takes colorOf, highlight, dim, tooltip, label,
 * onClick and restyles the seats without a new layout; a new seat list needs a new renderParliament call.
 *
 * Layout: all wedges share the same concentric rows; each wedge gets an angle proportional to its seats and fills
 * every row in proportion to the row's radius, so dots form clean arcs with even spacing across the house.
 * Inside a wedge, leaders take the front row from the middle out; everyone else follows sorted by group and name,
 * swept from left to right across all rows, so a Land forms a radial slice like a Landesgruppe.
 * No dependencies; works with light and dark pages (colours come from the page's CSS custom properties).
 */
'use strict';
(function (global) {
  const ORDER = ['AfD', 'CDU/CSU', 'BÜNDNIS 90/DIE GRÜNEN', 'SPD', 'Die Linke', 'fraktionslos'];
  const TOKENS = { 'CDU/CSU': '--cdu', 'SPD': '--spd', 'AfD': '--afd', 'BÜNDNIS 90/DIE GRÜNEN': '--gru', 'Die Linke': '--lin', 'fraktionslos': '--frl' };
  const FALLBACK = { 'CDU/CSU': '#2f2f2f', 'SPD': '#d7263d', 'AfD': '#1f8fd6', 'BÜNDNIS 90/DIE GRÜNEN': '#3f9a3f', 'Die Linke': '#c0397d', 'fraktionslos': '#8a8a8a' };
  const NS = 'http://www.w3.org/2000/svg';
  const R = 100;          // outer radius of the plenum, in viewBox units
  const INNER = 0.34;     // inner radius as a share of R
  const AISLE = 0.9;      // gap between wedges, in seat spacings at the middle row
  const EMPTY_TIPS = {
    regierung: '<b>Regierungsbank</b> – freier Platz',
    regierungLeer: '<b>Regierungsbank</b> – nicht Teil dieser Darstellung',
    bundesrat: '<b>Bundesrat</b> – nicht Teil dieses Datensatzes',
    praesidium: '<b>Präsidium</b> – freier Platz',
    praesidiumLeer: '<b>Präsidium</b> – nicht Teil dieser Darstellung',
    stenografen: '<b>Stenografischer Dienst</b> – nicht Teil dieses Datensatzes',
  };
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

  /* Seats: a pointer, and on hover/focus they grow; the dot is 0.68 of the seat spacing, so the card shows
   * between neighbours even when a seat is grown. Highlight = everything else fades to 25 % and the highlighted
   * seats get a thin halo with a gap of background colour in between, which reads on black CDU/CSU seats as
   * well as on light ones. Colours follow the host: pm-dark is set when the page behind the chart is dark. */
  const STYLE = `
.pm { position: relative; --pm-empty: var(--pm-furniture, #d6d6d1); --pm-rim: rgba(0,0,0,.14); --pm-halo: var(--accent, #2563eb); --pm-on: var(--text, #1f2328); }
.pm.pm-dark { --pm-empty: var(--pm-furniture, #4b4b53); --pm-rim: rgba(255,255,255,.32); --pm-halo: #8ab4ff; --pm-on: #f4f4f5; }
.pm svg { display: block; width: 100%; height: auto; overflow: visible; -webkit-tap-highlight-color: transparent; }
.pm .pm-seat { cursor: pointer; }
.pm .pm-info { cursor: help; }
.pm .pm-seat .d, .pm .pm-seat .hl, .pm .pm-info .e { transform-box: fill-box; transform-origin: center; transition: transform .12s ease-out, opacity .15s; }
.pm .pm-seat .d { stroke: var(--pm-rim); stroke-width: .3; }
.pm .pm-seat .h { fill: transparent; }
.pm .pm-seat .hl { fill: none; stroke: var(--pm-halo); stroke-width: .42; opacity: 0; }
.pm .pm-seat.pm-dim .d { opacity: .25; }
.pm .pm-seat.pm-hi .hl { opacity: 1; }
.pm .pm-seat:hover .d, .pm .pm-seat:hover .hl, .pm .pm-seat.pm-on .d, .pm .pm-seat.pm-on .hl,
.pm .pm-seat:focus-visible .d, .pm .pm-seat:focus-visible .hl, .pm .pm-info:hover .e, .pm .pm-info.pm-on .e { transform: scale(1.35); }
.pm .pm-seat.pm-dim:hover .d, .pm .pm-seat.pm-dim.pm-on .d { opacity: .7; }
.pm .pm-seat:hover .hl, .pm .pm-seat.pm-on .hl, .pm .pm-seat:focus-visible .hl { stroke: var(--pm-on); opacity: 1; }
.pm .pm-seat:focus { outline: none; }
.pm .pm-empty { fill: var(--pm-empty); }
.pm .pm-info:hover .e, .pm .pm-info.pm-on .e { fill: var(--muted, #6b7280); }
.pm .pm-furniture { fill: var(--pm-empty); }
.pm .pm-label { font: 500 4.2px Inter, system-ui, sans-serif; fill: var(--faint, #a1a1aa); letter-spacing: .02em; text-anchor: middle; }
.pm-tip { position: absolute; z-index: 20; pointer-events: none; max-width: min(280px, 90%); background: var(--card, #fff); color: var(--text, #1f2328);
  border: 1px solid var(--line, #e7e7e3); border-radius: 9px; padding: 6px 10px; font-size: 12.5px; line-height: 1.4;
  box-shadow: 0 4px 14px rgba(0,0,0,.12); white-space: normal; }
.pm-tip[hidden] { display: none; }
.pm-tip .pm-hint { color: var(--muted, #6b7280); font-size: 11.5px; margin-top: 2px; }
.pm.pm-dark .pm-tip { box-shadow: 0 4px 14px rgba(0,0,0,.5); }
@media (prefers-reduced-motion: reduce) { .pm .pm-seat .d, .pm .pm-seat .hl, .pm .pm-info .e { transition: none; } }`;

  /* true when the first opaque background behind the element is dark */
  function onDark(node) {
    for (let n = node; n && n.nodeType === 1; n = n.parentElement) {
      const m = getComputedStyle(n).backgroundColor.match(/[\d.]+/g);
      if (!m || (m.length > 3 && +m[3] === 0)) continue;
      const [r, g, b] = m.slice(0, 3).map(v => +v / 255);
      return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.45;
    }
    return false;
  }

  function injectStyle() {
    if (document.getElementById('pm-style')) return;
    const s = document.createElement('style');
    s.id = 'pm-style';
    s.textContent = STYLE;
    document.head.appendChild(s);
  }

  const asTest = x => x == null ? () => false : typeof x === 'function' ? x : s => x.has(s.id);

  /* rows and angles of the fraction wedges */
  function layoutWedges(groups) {
    const total = groups.reduce((a, g) => a + g.seats.length, 0);
    if (!total) return [];
    const rIn = INNER * R;
    const n = groups.length;
    let rows = 2;
    for (; rows < 60; rows++) {
      const d = (R - rIn) / (rows - 1);
      const gap = n > 1 ? AISLE * d / ((R + rIn) / 2) : 0;
      const span = Math.PI - gap * (n - 1) - d / R;  // half a seat of margin at both ends of the outer row
      let cap = 0;
      for (let i = 0; i < rows; i++) cap += Math.floor(span * (rIn + i * d) / d);
      if (cap >= total) break;
    }
    const d = (R - rIn) / (rows - 1);
    const radii = Array.from({ length: rows }, (_, i) => rIn + i * d);
    const sumR = radii.reduce((a, b) => a + b, 0);
    const gap = n > 1 ? AISLE * d / ((R + rIn) / 2) : 0;
    const margin = d / R / 2;
    const span = Math.PI - gap * (n - 1) - 2 * margin;
    const out = [];
    let t0 = margin;
    for (const g of groups) {
      const a = span * g.seats.length / total;
      // seats per row in proportion to the row's length (largest remainder), so spacing is even everywhere
      const quota = radii.map(r => g.seats.length * r / sumR);
      const k = quota.map(Math.floor);
      let rest = g.seats.length - k.reduce((x, y) => x + y, 0);
      const order = quota.map((q, i) => [q - Math.floor(q), i]).sort((x, y) => y[0] - x[0] || y[1] - x[1]);
      for (let j = 0; rest > 0; j = (j + 1) % rows, rest--) k[order[j][1]]++;
      const pos = [];
      radii.forEach((r, i) => {
        for (let j = 0; j < k[i]; j++) {
          const t = t0 + (j + 0.5) * a / k[i];
          pos.push({ row: i, t, x: -r * Math.cos(t), y: r * Math.sin(t) });
        }
      });
      out.push({ group: g, pos, from: t0, to: t0 + a });
      t0 += a + gap;
    }
    return { wedges: out, d };
  }

  /* assign a wedge's seats to its positions: leaders front row from the middle out, the rest swept left to right */
  function seatWedge(w) {
    const mid = (w.from + w.to) / 2;
    const cmpName = (a, b) => String(a.sort ?? a.name ?? '').localeCompare(String(b.sort ?? b.name ?? ''), 'de') || String(a.id).localeCompare(String(b.id));
    const leaders = w.group.seats.filter(s => s.lead != null).sort((a, b) => a.lead - b.lead || cmpName(a, b));
    const others = w.group.seats.filter(s => s.lead == null)
      .sort((a, b) => String(a.group ?? '￿').localeCompare(String(b.group ?? '￿'), 'de') || cmpName(a, b));
    const front = [...w.pos].sort((a, b) => a.row - b.row || Math.abs(a.t - mid) - Math.abs(b.t - mid) || a.t - b.t);
    const taken = new Set(front.slice(0, leaders.length));
    const sweep = w.pos.filter(p => !taken.has(p)).sort((a, b) => a.t - b.t || a.row - b.row);
    return [...leaders.map((s, i) => [s, front[i]]), ...others.map((s, i) => [s, sweep[i]])];
  }

  /* rows of a top block: arcs around a centre far below, so the rows curve towards the plenum as on bundestag.de */
  function benchRows(n, d, side, minRows) {
    const C = 2.6 * R;             // centre of the bench arcs, below the plenum centre
    const y0 = -0.2 * R;           // front row at the middle
    const x0 = 0.19 * R, x1 = 0.86 * R;
    const out = [];
    const rows = [];
    for (let i = 0; out.length < n || i < minRows; i++) {
      const rho = C - y0 + i * d;
      const b0 = Math.asin(x0 / rho), b1 = Math.asin(Math.min(1, (x1 + i * d * 0.25) / rho));
      const k = Math.max(1, Math.floor((b1 - b0) * rho / d));
      const row = [];
      for (let j = 0; j < k; j++) {
        const b = b1 - j * (b1 - b0) / Math.max(1, k - 1);  // from the outside in
        const p = { x: side * rho * Math.sin(b), y: C - rho * Math.cos(b), row: i };
        row.push(p);
      }
      rows.push(row);
      out.push(...row);
      if (i > 40) break;
    }
    // fill from the front row, and within a row from the middle out
    out.sort((a, b) => a.row - b.row || Math.abs(a.x) - Math.abs(b.x));
    return { pos: out.slice(0, Math.max(n, 0)), all: out, rows: rows.length };
  }

  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  }

  function renderParliament(host, seats, options = {}) {
    injectStyle();
    let opts = { ...options };
    const order = opts.order || ORDER;
    const byFraction = new Map();
    for (const s of seats) {
      const f = s.fraction || 'fraktionslos';
      if (!byFraction.has(f)) byFraction.set(f, []);
      byFraction.get(f).push(s);
    }
    const known = order.filter(f => byFraction.has(f));
    const unknown = [...byFraction.keys()].filter(f => !order.includes(f)).sort();
    const last = known[known.length - 1] === 'fraktionslos' ? [known.pop()] : [];
    const groups = [...known, ...unknown, ...last].map(f => ({ fraction: f, seats: byFraction.get(f) }));

    const { wedges = [], d = (R * (1 - INNER)) / 12 } = layoutWedges(groups) || {};
    const dot = d * 0.34;  // a clear gap between neighbours, even with a seat grown on hover
    const placed = [];  // {seat, x, y, bench}
    for (const w of wedges) for (const [s, p] of seatWedge(w)) placed.push({ seat: s, x: p.x, y: p.y, bench: 'plenum' });

    const gov = opts.government || [];
    const nBR = opts.bundesrat ?? Math.max(gov.length, 24);
    const minRows = 3;
    const left = benchRows(gov.length, d, -1, minRows);
    const right = benchRows(nBR, d, 1, Math.max(minRows, left.rows));
    left.pos.forEach((p, i) => placed.push({ seat: gov[i], x: p.x, y: p.y, bench: 'regierung' }));
    const leftEmpty = left.all.filter(p => !left.pos.includes(p));

    const pres = opts.presidium || [];
    const presPos = [[0, -0.28 * R], [-0.075 * R, -0.28 * R], [0.075 * R, -0.28 * R], [-0.04 * R, -0.5 * R], [0.04 * R, -0.5 * R]];
    for (let i = presPos.length; i < pres.length; i++) presPos.push([(i % 2 ? -1 : 1) * (0.04 + 0.08 * Math.floor((i - 3) / 2)) * R, -0.5 * R]);
    pres.forEach((s, i) => placed.push({ seat: s, x: presPos[i][0], y: presPos[i][1], bench: 'praesidium', chair: i === 0 }));

    const top = Math.min(-0.55 * R, ...left.all.map(p => p.y), ...right.all.map(p => p.y)) - d * 1.2;
    const pad = d;
    const vb = [-R - pad, top, 2 * (R + pad), R + pad - top];

    host.classList.add('pm');
    if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
    host.innerHTML = '';
    const svg = el('svg', { viewBox: vb.map(v => +v.toFixed(2)).join(' '), role: 'group', tabindex: '-1', 'aria-label': opts.title || 'Sitzverteilung im Bundestag' }, host);
    // everything that is not a person's seat, in one group (svg.children stays [furniture, seats] for callers that
    // drop it to show only the plenum): the drawing is hidden from screen readers, the seat blocks are labelled
    const furniture = el('g', { class: 'pm-house' }, svg);
    const drawing = el('g', { 'aria-hidden': 'true' }, furniture);
    // desk of the Präsidium, lectern
    el('rect', { class: 'pm-furniture', x: (-0.03 * R).toFixed(2), y: (-0.435 * R).toFixed(2), width: (0.06 * R).toFixed(2), height: (0.1 * R).toFixed(2), rx: 0.8 }, drawing);
    el('rect', { class: 'pm-furniture', x: (-0.018 * R).toFixed(2), y: (-0.17 * R).toFixed(2), width: (0.036 * R).toFixed(2), height: (0.036 * R).toFixed(2), rx: 0.5 }, drawing);
    const labelY = top + d * 0.2;
    el('text', { class: 'pm-label', x: (-0.52 * R).toFixed(2), y: labelY.toFixed(2) }, drawing).textContent = 'Regierungsbank';
    el('text', { class: 'pm-label', x: (0.52 * R).toFixed(2), y: labelY.toFixed(2) }, drawing).textContent = 'Bundesrat';
    el('text', { class: 'pm-label', x: 0, y: labelY.toFixed(2) }, drawing).textContent = 'Präsidium';

    // seats without a person: the rest of the Regierungsbank, the Bundesrat, the Präsidium's empty chairs and the
    // stenographers. Each has a tooltip (hover, tap) saying what it is; one aria-label per block for screen readers.
    const tipOf = { ...EMPTY_TIPS, ...(gov.length ? {} : { regierung: EMPTY_TIPS.regierungLeer }), ...(pres.length ? {} : { praesidium: EMPTY_TIPS.praesidiumLeer }), ...(opts.emptyTips || {}) };
    const infos = [];
    function infoBlock(kind, label, points) {
      if (!points.length) return;
      const g = el('g', { role: 'img', 'aria-label': label }, furniture);
      for (const [x, y, r] of points) {
        const s = el('g', { class: 'pm-info', 'aria-hidden': 'true' }, g);
        el('circle', { class: 'pm-empty e', cx: x.toFixed(2), cy: y.toFixed(2), r: r.toFixed(2) }, s);
        const p = { x, y, kind, node: s };
        s._pm = p;
        infos.push(p);
      }
    }
    infoBlock('regierung', `Regierungsbank: ${leftEmpty.length} freie Plätze`, leftEmpty.map(p => [p.x, p.y, dot]));
    if (nBR > 0) infoBlock('bundesrat', `Bundesrat: ${right.all.length} Plätze, nicht Teil dieses Datensatzes`, right.all.map(p => [p.x, p.y, dot]));
    const presEmpty = [];
    for (let i = pres.length; i < 5; i++) presEmpty.push([presPos[i][0], presPos[i][1], i === 0 ? dot * 1.35 : dot]);
    infoBlock('praesidium', 'Präsidium: freie Plätze', presEmpty);
    infoBlock('stenografen', 'Stenografischer Dienst', [0, 1, 2, 3].map(i => [(i - 1.5) * d * 0.95, 0.1 * R, dot * 0.85]));

    const nodes = [];
    const seatsG = el('g', {}, svg);
    for (const p of placed) {
      const g = el('g', { class: 'pm-seat', tabindex: '-1', role: 'button' }, seatsG);
      el('circle', { class: 'h', cx: p.x.toFixed(2), cy: p.y.toFixed(2), r: (d * 0.55).toFixed(2) }, g);
      const r = p.chair ? dot * 1.35 : dot;
      el('circle', { class: 'hl', cx: p.x.toFixed(2), cy: p.y.toFixed(2), r: (r + d * 0.12).toFixed(2) }, g);
      el('circle', { class: 'd', cx: p.x.toFixed(2), cy: p.y.toFixed(2), r: r.toFixed(2) }, g);
      p.node = g;
      g._pm = p;
      nodes.push(p);
    }
    if (nodes.length) nodes[0].node.setAttribute('tabindex', '0');

    const tip = document.createElement('div');
    tip.className = 'pm-tip';
    tip.hidden = true;
    tip.setAttribute('role', 'status');
    host.appendChild(tip);

    const defaultLabel = s => [s.name, s.fraction].filter(Boolean).join(', ');
    const defaultTip = s => `<b>${esc(s.name)}</b>${s.fraction ? `<br><span style="color:var(--muted,#6b7280)">${esc(s.fraction)}</span>` : ''}`;
    const benchName = { regierung: 'Regierungsbank', praesidium: 'Präsidium' };

    function style() {
      const colorOf = opts.colorOf || (s => {
        const t = TOKENS[s.fraction || 'fraktionslos'];
        return (t && getComputedStyle(host).getPropertyValue(t).trim()) || FALLBACK[s.fraction || 'fraktionslos'] || '#8a8a8a';
      });
      host.classList.toggle('pm-dark', onDark(host));
      const hi = asTest(opts.highlight), dim = asTest(opts.dim);
      const label = opts.label || defaultLabel;
      for (const p of nodes) {
        p.node.querySelector('.d').setAttribute('fill', colorOf(p.seat) || '#8a8a8a');
        p.node.classList.toggle('pm-hi', !!hi(p.seat));
        p.node.classList.toggle('pm-dim', !!dim(p.seat));
        p.node.setAttribute('aria-label', label(p.seat) + (benchName[p.bench] ? ` (${benchName[p.bench]})` : ''));
      }
    }
    style();

    let active = null;      // the node whose tooltip is shown after a tap or focus
    let pointer = 'mouse';
    function show(p, pinned) {
      tip.innerHTML = p.kind ? tipOf[p.kind] : (opts.tooltip || defaultTip)(p.seat) + (pinned && pointer !== 'mouse' && opts.onClick ? `<div class="pm-hint">${esc(opts.tapHint || 'Nochmals tippen zum Öffnen')}</div>` : '');
      tip.hidden = false;
      const hb = host.getBoundingClientRect(), sb = p.node.querySelector('.d, .e').getBoundingClientRect();
      const tw = tip.offsetWidth, th = tip.offsetHeight;
      let x = sb.left + sb.width / 2 - hb.left - tw / 2;
      x = Math.max(0, Math.min(hb.width - tw, x));
      let y = sb.top - hb.top - th - 8;
      if (y < 0) y = sb.bottom - hb.top + 8;
      tip.style.left = x + 'px';
      tip.style.top = y + 'px';
    }
    function hide() { tip.hidden = true; }
    function setActive(p) {
      if (active) active.node.classList.remove('pm-on');
      active = p;
      if (p) p.node.classList.add('pm-on');
    }

    let roving = nodes[0];
    function rove(p) {  // the one seat reachable with Tab
      if (roving) roving.node.setAttribute('tabindex', '-1');
      roving = p;
      p.node.setAttribute('tabindex', '0');
    }
    const seatOf = e => e.target.closest && e.target.closest('.pm-seat');
    const infoOf = e => e.target.closest && e.target.closest('.pm-info');
    svg.addEventListener('pointerdown', e => { pointer = e.pointerType || 'mouse'; });
    svg.addEventListener('pointerover', e => {
      if (e.pointerType && e.pointerType !== 'mouse') return;
      const g = seatOf(e) || infoOf(e);
      if (g) show(g._pm, false);
    });
    svg.addEventListener('pointerout', e => {
      if (e.pointerType && e.pointerType !== 'mouse') return;
      const g = seatOf(e) || infoOf(e);
      if (g && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('.pm-seat, .pm-info') === g)) {
        if (active) show(active, true); else hide();
      }
    });
    svg.addEventListener('click', e => {
      const info = infoOf(e);
      if (info) { if (pointer !== 'mouse') { setActive(info._pm); show(info._pm, false); } return; }  // a tap shows what it is
      const g = seatOf(e);
      if (!g) { setActive(null); hide(); return; }
      const p = g._pm;
      rove(p);
      if (pointer !== 'mouse' && active !== p) {  // touch or pen: first tap shows, second tap on the same seat opens
        setActive(p);
        show(p, true);
        return;
      }
      if (opts.onClick) opts.onClick(p.seat, e);
    });
    const outside = e => { if (!host.contains(e.target)) { setActive(null); hide(); } };
    document.addEventListener('pointerdown', outside);

    function move(from, dx, dy) {
      let best = null, score = Infinity;
      for (const p of nodes) {
        if (p === from) continue;
        const vx = p.x - from.x, vy = p.y - from.y;
        const along = vx * dx + vy * dy, perp = Math.abs(vx * dy - vy * dx);
        if (along < d * 0.3) continue;
        const s = along + 2.5 * perp;
        if (s < score) { score = s; best = p; }
      }
      return best;
    }
    svg.addEventListener('keydown', e => {
      const g = seatOf(e);
      if (!g) return;
      const p = g._pm;
      const dirs = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
      let next = null;
      if (dirs[e.key]) next = move(p, ...dirs[e.key]);
      else if (e.key === 'Home') next = nodes[0];
      else if (e.key === 'End') next = nodes[nodes.length - 1];
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (opts.onClick) opts.onClick(p.seat, e); return; }
      else if (e.key === 'Escape') { hide(); return; }
      else return;
      e.preventDefault();
      if (next) { rove(next); next.node.focus(); }
    });
    let pressed = false;  // focus that comes from a click or tap, not from the keyboard
    svg.addEventListener('pointerdown', () => { pressed = true; setTimeout(() => { pressed = false; }, 600); });
    svg.addEventListener('focusin', e => { const g = seatOf(e); if (g && !pressed) show(g._pm, false); });
    svg.addEventListener('focusout', e => { if (!(e.relatedTarget && svg.contains(e.relatedTarget)) && !pressed) { setActive(null); hide(); } });

    return {
      svg,
      update(o) { opts = { ...opts, ...o }; style(); if (active) show(active, true); },
      seat(id) { return nodes.filter(p => p.seat.id === id).map(p => p.node); },
      destroy() { document.removeEventListener('pointerdown', outside); host.innerHTML = ''; host.classList.remove('pm'); },
    };
  }

  global.renderParliament = renderParliament;
  global.PARLIAMENT_ORDER = ORDER;
})(typeof window !== 'undefined' ? window : globalThis);
