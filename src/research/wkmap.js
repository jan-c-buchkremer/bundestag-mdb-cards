// The map of the 299 Wahlkreise on the Orte page (places.py `bund_page`), moved there from the Abgeordnete page
// (docs/plan.md 12.2): a place is an entity of its own, and its page owns its views. The shapes come from
// wahlkreise.json (scripts/wahlkreise_geo.py), fetched when the map is shown; the colours (the fraction of each
// Wahlkreis's direct seat) and the names come from the page data, computed in Python. Every click leads to the
// Wahlkreis's page: with a mouse at once, on a touch screen the first tap selects it and shows the link, a second
// tap on the same Wahlkreis follows it.
'use strict';

(function (global) {
  const MAX_ZOOM = 24;  // the smallest Wahlkreise (Berlin, Munich) need about this much to fill the map
  const NO_SEAT = '#d4d4cf';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  // opts: {box, strip, legend, credit, src, wahlkreise: {nr: {name, land, fill, fraction}}, lands: {code: name},
  //        legendItems: [[label, cssVar or null]], href: nr => url, selected: nr or null, onSelect: nr => void}
  function mount(opts) {
    const { box, strip } = opts;
    const W = opts.wahlkreise;
    let paths = null, zoom = null, sel = opts.selected ?? null, hover = null, lit = null, touched = false;

    function info(nr) {
      const w = W[nr];
      return w ? `<b>${esc(nr)} · ${esc(w.name)}</b><br><span class="k">${esc(opts.lands[w.land] || '')}${w.holder ? ` · ${esc(w.holder)}` : ''}</span>` : '';
    }

    function style() {
      if (!paths) return;
      for (const [nr, p] of paths) {
        p.classList.toggle('dim', !!lit && !lit.has(nr));
        p.classList.toggle('sel', sel === nr);
      }
      // outlines on top of the neighbours, as copies: moving the path itself under the pointer would swallow clicks
      for (const [id, nr] of [['ovsel', sel], ['ovhover', hover]]) {
        const o = box.querySelector(`#${id}`), src = nr != null && paths.get(nr);
        o.style.display = src ? '' : 'none';
        if (src) o.querySelectorAll('path').forEach(x => x.setAttribute('d', src.getAttribute('d')));
      }
      const tip = box.querySelector('.info'), nr = hover ?? sel;
      tip.hidden = nr == null;
      if (nr != null) tip.innerHTML = info(nr);
      const w = sel != null && W[sel];
      strip.hidden = !w;
      if (w) strip.innerHTML = `<div class="t">${info(sel)}</div><a class="go" href="${esc(opts.href(sel))}">Zur Seite des Wahlkreises →</a>`;
    }

    function select(nr, zoomTo) {
      sel = nr;
      if (zoomTo && nr != null && zoom) zoom.to(nr, true);
      style();
      if (opts.onSelect) opts.onSelect(nr);
    }

    function wire(svg) {
      const nrOf = e => e.target.closest && e.target.closest('path[data-nr]') ? +e.target.closest('path[data-nr]').dataset.nr : null;
      svg.addEventListener('pointerdown', e => { touched = e.pointerType !== 'mouse'; });
      svg.addEventListener('pointerover', e => { if (e.pointerType === 'mouse') { hover = nrOf(e); style(); } });
      svg.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') { hover = null; style(); } });
      svg.addEventListener('click', e => {
        const nr = nrOf(e);
        if (nr == null || !W[nr]) return;
        if (!touched || sel === nr) { location.href = opts.href(nr); return; }
        select(nr, false);
      });
    }

    const ready = fetch(opts.src).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(geo => {
      const shapes = Object.entries(geo.paths).map(([nr, d]) => `<path data-nr="${nr}" d="${d}"><title>${esc(nr)} ${esc(W[nr]?.name || '')}</title></path>`).join('');
      box.innerHTML = `<svg viewBox="${geo.viewBox}" role="img" aria-label="Karte der 299 Wahlkreise, gefärbt nach der Fraktion des direkt gewählten Mitglieds"><g>${shapes}</g><g class="ov"><g id="ovsel"><path class="case"></path><path class="sel"></path></g><g id="ovhover"><path class="case"></path><path class="hover"></path></g></g></svg><div class="info" hidden></div>`
        + '<div class="mapzoom"><button type="button" data-z="in" aria-label="Karte vergrößern" title="Vergrößern">+</button><button type="button" data-z="out" aria-label="Karte verkleinern" title="Verkleinern">−</button><button type="button" data-z="reset" aria-label="Ganze Karte zeigen" title="Ganze Karte">⟲</button></div>';
      if (opts.credit) opts.credit.innerHTML = `Karte: ${esc(geo.attribution)}, <a href="${esc(geo.source)}">${esc(geo.licence)}</a>, vereinfacht.`;
      if (opts.legend) opts.legend.innerHTML = opts.legendItems.map(([label, v]) => `<span><i class="dot" style="background:${v ? css(v) : NO_SEAT}"></i>${esc(label)}</span>`).join('');
      paths = new Map([...box.querySelectorAll('path[data-nr]')].map(p => [+p.dataset.nr, p]));
      for (const [nr, p] of paths) p.setAttribute('fill', W[nr]?.fill ? css(W[nr].fill) : NO_SEAT);
      const svg = box.querySelector('svg');
      wire(svg);
      zoom = mapZoom(svg, box, geo.viewBox, nr => paths.get(nr));
      style();
      if (sel != null) zoom.to(sel, false);
    }).catch(() => { box.innerHTML = '<div class="maploading">Die Karte konnte nicht geladen werden.</div>'; });

    return {
      ready,
      select,
      // highlight a set of Wahlkreis numbers (the place search's hits), null for all
      light(nrs) { lit = nrs && nrs.size ? nrs : null; style(); },
      zoomTo(nrs) { if (zoom) zoom.toAll(nrs); },
    };
  }

  // Zoom and pan by changing the viewBox (strokes do not scale): wheel, pinch, drag, the +/−/⟲ buttons, and
  // to(nr) / toAll(nrs) for Wahlkreise. The aspect ratio never changes, so the map keeps its height on the phone.
  function mapZoom(svg, box, viewBox, pathOf) {
    const base = viewBox.split(/[\s,]+/).map(Number);
    let vb = base.slice(), frame = 0;
    const reduce = matchMedia('(prefers-reduced-motion: reduce)');
    function clamp([x, y, w]) {
      w = Math.min(base[2], Math.max(base[2] / MAX_ZOOM, w));
      const h = w * base[3] / base[2];
      return [Math.min(Math.max(x, base[0]), base[0] + base[2] - w), Math.min(Math.max(y, base[1]), base[1] + base[3] - h), w, h];
    }
    const buttons = {};
    box.querySelectorAll('.mapzoom button').forEach(b => { buttons[b.dataset.z] = b; });
    function apply(v) {
      vb = clamp(v);
      svg.setAttribute('viewBox', vb.map(t => +t.toFixed(3)).join(' '));
      const zoomed = vb[2] < base[2] * 0.999;
      box.classList.toggle('zoomed', zoomed);
      buttons.out.disabled = buttons.reset.disabled = !zoomed;
      buttons.in.disabled = vb[2] <= base[2] / MAX_ZOOM * 1.001;
    }
    function animate(target) {
      cancelAnimationFrame(frame);
      target = clamp(target);
      if (reduce.matches) return apply(target);
      const from = vb.slice(), t0 = performance.now();
      const c0 = [from[0] + from[2] / 2, from[1] + from[3] / 2], c1 = [target[0] + target[2] / 2, target[1] + target[3] / 2];
      const step = now => {
        const t = Math.min(1, (now - t0) / 320), e = 1 - Math.pow(1 - t, 3);
        const w = Math.exp(Math.log(from[2]) + (Math.log(target[2]) - Math.log(from[2])) * e);  // log scale: in and out feel alike
        const h = w * base[3] / base[2];
        apply([c0[0] + (c1[0] - c0[0]) * e - w / 2, c0[1] + (c1[1] - c0[1]) * e - h / 2, w]);
        if (t < 1) frame = requestAnimationFrame(step);
      };
      frame = requestAnimationFrame(step);
    }
    const toUser = (cx, cy) => {
      const m = svg.getScreenCTM();
      return m ? new DOMPoint(cx, cy).matrixTransform(m.inverse()) : { x: vb[0] + vb[2] / 2, y: vb[1] + vb[3] / 2 };
    };
    const around = (f, p, v = vb) => [p.x - (p.x - v[0]) / f, p.y - (p.y - v[1]) / f, v[2] / f];
    const centre = () => ({ x: vb[0] + vb[2] / 2, y: vb[1] + vb[3] / 2 });

    box.querySelector('.mapzoom').addEventListener('click', e => {
      const z = e.target.closest('button')?.dataset.z;
      if (z === 'in') animate(around(1.8, centre()));
      else if (z === 'out') animate(around(1 / 1.8, centre()));
      else if (z === 'reset') animate(base);
    });
    svg.addEventListener('wheel', e => {
      e.preventDefault();
      cancelAnimationFrame(frame);
      const dy = e.deltaY * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1);
      apply(around(Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0022)), toUser(e.clientX, e.clientY)));  // ctrlKey: trackpad pinch
    }, { passive: false });

    // pointers: one drags (after a few pixels, so a click still selects), two pinch
    const down = new Map();
    let moved = false, last = null;
    const mid = () => { const [a, b] = [...down.values()]; return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, d: Math.hypot(a.x - b.x, a.y - b.y) }; };
    svg.addEventListener('pointerdown', e => {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      down.set(e.pointerId, { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY });
      if (down.size === 1) moved = false;
      last = down.size === 2 ? mid() : null;
      cancelAnimationFrame(frame);
    });
    svg.addEventListener('pointermove', e => {
      const p = down.get(e.pointerId);
      if (!p) return;
      const px = p.x, py = p.y;
      p.x = e.clientX; p.y = e.clientY;
      if (down.size === 2) {
        const m = mid();
        if (last && last.d > 0) {
          const a = toUser(last.x, last.y), b = toUser(m.x, m.y);
          apply(around(m.d / last.d, b, [vb[0] + (a.x - b.x), vb[1] + (a.y - b.y), vb[2]]));
        }
        last = m;
        moved = true;
        if (!svg.hasPointerCapture(e.pointerId)) svg.setPointerCapture(e.pointerId);
        return;
      }
      if (!moved && Math.hypot(p.x - p.x0, p.y - p.y0) < 5) return;
      if (!moved) { moved = true; svg.setPointerCapture(e.pointerId); box.classList.add('drag'); }
      const a = toUser(px, py), b = toUser(p.x, p.y);
      apply([vb[0] - (b.x - a.x), vb[1] - (b.y - a.y), vb[2]]);
    });
    const up = e => {
      down.delete(e.pointerId);
      last = down.size === 2 ? mid() : null;
      if (!down.size) box.classList.remove('drag');
    };
    svg.addEventListener('pointerup', up);
    svg.addEventListener('pointercancel', e => { up(e); moved = false; });
    // a drag or pinch is not a click on the Wahlkreis under the pointer
    svg.addEventListener('click', e => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);

    apply(base);
    function frameOf(boxes) {  // the boxes in the middle with room around them
      const x0 = Math.min(...boxes.map(b => b.x)), y0 = Math.min(...boxes.map(b => b.y));
      const x1 = Math.max(...boxes.map(b => b.x + b.width)), y1 = Math.max(...boxes.map(b => b.y + b.height));
      const w = Math.max((x1 - x0) * 1.6, (y1 - y0) * 1.6 * base[2] / base[3]);
      const h = w * base[3] / base[2];
      return [(x0 + x1) / 2 - w / 2, (y0 + y1) / 2 - h / 2, w];
    }
    return {
      to(nr, smooth) {
        const p = pathOf(nr);
        if (!p) return;
        const bb = p.getBBox();
        const w = Math.max(bb.width * 2.6, bb.height * 2.6 * base[2] / base[3]);
        const h = w * base[3] / base[2];
        const t = [bb.x + bb.width / 2 - w / 2, bb.y + bb.height / 2 - h / 2, w];
        smooth ? animate(t) : apply(t);
      },
      toAll(nrs) {
        const boxes = [...nrs].map(pathOf).filter(Boolean).map(p => p.getBBox());
        animate(boxes.length ? frameOf(boxes) : base);
      },
    };
  }

  global.WkMap = { mount };
})(window);
