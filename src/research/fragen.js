// The research view of regierung/index.html (questions.py, docs/plan.md 12.5): every single question, one list per
// kind, each loaded from regierung/<kind>.json only when the kind is chosen (#liste=<kind>). The filters are the
// visual controls Python drew from the same JSON (controls.py, questions.research_panel): Fraktion, Ressort, Stand,
// for Kleine Anfragen the answer time, and the months; controls.js keeps their state in the URL and counts, this
// script gives it the rows (`tokens`, the same values as questions.facets) and draws them. Every row links its
// sources (DIP, the PDF, the asker's card, and for oral questions the protocol and the speech page). No ranking:
// newest first. Runs in Node too (tokens, for tests/test_questions.py).
'use strict';
(() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const sd = d => d ? `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}` : '';
  const DIP_DOC = id => `https://dip.bundestag.de/drucksache/x/${encodeURIComponent(id)}`;
  const DIP_VORGANG = id => `https://dip.bundestag.de/vorgang/${encodeURIComponent(id)}`;
  // as data.drucksache_pdf: 21/6130 -> …/btd/21/061/2106130.pdf
  const pdfOf = number => { const [wp, n] = number.split('/'); const n5 = String(+n).padStart(5, '0'); return `https://dserver.bundestag.de/btd/${wp}/${n5.slice(0, 3)}/${wp}${n5}.pdf`; };
  const SHORT = { 'BÜNDNIS 90/DIE GRÜNEN': 'Grüne' };
  // as urls.slug: lowercase ASCII, umlauts spelled out, any other character a hyphen
  const UML = { 'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss' };
  const slug = s => String(s).replace(/[äöüÄÖÜß]/g, c => UML[c]).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  const frist = days => days == null ? 'offen' : days <= 14 ? 'bis-14-tage' : days <= 28 ? '15-bis-28-tage' : 'mehr-als-28-tage';

  // what the filters see in a row: the same values as questions.facets
  function tokens(d, r) {
    const k = d.kind, tok = t => (t && d.tokens[t] ? [d.tokens[t]] : []);
    let date, f;
    if (k === 'kleine-anfragen') {
      const [doc, , fractions, , ressort, answer] = r;
      date = d.docs[doc][2];
      f = { fraktion: fractions.filter(x => d.tokens[x]).map(x => d.tokens[x]), ressort: ressort != null ? d.slugs.ressorts[ressort] : '',
        stand: answer ? 'beantwortet' : 'offen', frist: frist(answer ? answer[1] : null) };
    } else if (k === 'schriftliche-fragen' || k === 'muendliche-fragen') {
      const [, own, , status, ressort, doc, asker] = r;
      date = own || (doc != null ? d.docs[doc][2] : '');
      f = { fraktion: tok(asker != null ? d.persons[asker][2] : null), ressort: ressort != null ? d.slugs.ressorts[ressort] : '',
        stand: status != null ? d.slugs.statuses[status] : 'ohne-stand', frist: '' };
    } else {
      const [, when, who, role] = r;
      date = when;
      f = { fraktion: tok(who != null && !role ? d.persons[who][2] : null), ressort: role ? slug(role) : '',
        stand: role ? 'antwort-der-bundesregierung' : 'frage', frist: '' };
    }
    date = date || '';
    return { ...f, monat: date.slice(0, 7), tag: date.slice(0, 10) };
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { tokens };
    return;
  }
  const root = document.getElementById('fragen');
  if (!root) return;
  const scope = root.closest('.ctl-scope');
  const list = root.querySelector('#flist');
  const cache = {};
  let kind = null;

  const a = (href, text, title) => href ? `<a href="${esc(href)}"${title ? ` title="${esc(title)}"` : ''}>${text}</a>` : text;
  const person = (d, i) => {
    const p = d.persons[i];
    if (!p) return '';
    const label = esc(p[1]) + (p[2] ? ` <span class="faint">${esc(SHORT[p[2]] || p[2])}</span>` : '');
    return p[3] ? a(`../${encodeURIComponent(p[0])}.html`, label) : label;
  };
  const docLinks = (d, i, label) => {
    const [number, id, , pdf] = d.docs[i];
    return `${label} ${a(id ? DIP_DOC(id) : null, esc(number), 'Drucksache im DIP')} (${a(pdf || pdfOf(number), 'PDF')})`;
  };
  const speechHref = href => `../${href}`;  // questions.py writes urls.speech, the one rule for a speech's page
  const sittingHref = (sid, pos) => `../sitzungen/${sid.replaceAll('/', '-')}.html${pos != null ? `#top-${pos}` : ''}`;

  // one view per row: what the filters look at (controls.js) and what the list shows
  function views(d) {
    const k = d.kind;
    return d.rows.map(r => {
      const tok = tokens(d, r);
      let title, names, html;
      if (k === 'kleine-anfragen') {
        const [doc, t, fractions, askers, , answer, vorgang] = r;
        title = t;
        names = askers.map(i => d.persons[i]?.[1] || '');
        html = () => {
          const who = askers.slice(0, 3).map(i => person(d, i)).join(', ') + (askers.length > 3 ? ` und ${askers.length - 3} weitere` : '');
          const ans = answer ? `${docLinks(d, answer[0], 'Antwort')} nach ${answer[1]} Tagen` : '<span class="tag warn">noch keine Antwort im Datenbestand</span>';
          return [fractions.map(f => esc(SHORT[f] || f)).join(', ') + (who ? ` · ${who}` : ''), ans,
            [docLinks(d, doc, 'Anfrage'), vorgang ? a(DIP_VORGANG(vorgang), 'Vorgang im DIP') : ''].filter(Boolean).join(' · ')];
        };
      } else if (k === 'schriftliche-fragen' || k === 'muendliche-fragen') {
        const [vorgang, , t, , ressort, doc, asker, answer, by = []] = r;
        const p = asker != null ? d.persons[asker] : null;
        title = t;
        // the search finds a question by its asker and by who answered it (questions.py: by ministry)
        names = [...(p ? [p[1]] : []), ...by.map(([i]) => d.persons[i]?.[1] || '')];
        html = () => {
          const who = p ? `Gefragt von ${person(d, asker)}` : '';
          const answered = by.length ? `Antwort${by.length > 1 ? ' von einer der Genannten' : ''}: ${by.map(([i, sp]) => person(d, i) + (sp ? ` (${a(speechHref(sp), 'Antwort im Protokoll')})` : '')).join(', ')}` : '';
          const plenum = answer ? [answer[0] ? a(sittingHref(answer[0], answer[1]), `Antwort in der Fragestunde, Plenarprotokoll ${esc(answer[4])}${answer[2] ? `, S. ${esc(answer[2])}` : ''}`) : `Plenarprotokoll ${esc(answer[4])}${answer[2] ? `, S. ${esc(answer[2])}` : ''}`, answer[3] ? a(answer[3], 'Protokoll (PDF)') : ''].filter(Boolean).join(' · ') : '';
          return [[who, d.ressorts[ressort] ? esc(d.ressorts[ressort]) : '', answered].filter(Boolean).join(' · '), plenum,
            [a(DIP_VORGANG(vorgang), 'Frage im DIP'), doc != null ? docLinks(d, doc, 'Sammeldrucksache') : ''].filter(Boolean).join(' · ')];
        };
      } else {
        const [speech, , who, role, sitting, position, agenda, text] = r;
        const p = d.persons[who];
        title = text;
        names = p ? [p[1]] : [];
        html = () => [`${person(d, who)}${role ? ` · ${esc(role)}` : ''}`, '',
          [a(speechHref(speech), 'Text im Protokoll'), sitting ? a(sittingHref(sitting, position), esc(agenda || 'Sitzung')) : ''].filter(Boolean).join(' · ')];
      }
      const { monat, tag, ...rest } = tok;
      return {
        date: tag, title, html,
        tok: Object.fromEntries(Object.entries({ ...rest, monat, tag }).map(([key, v]) => [key, Array.isArray(v) ? v : v ? [v] : []])),
        w: '', text: [title, ...names].join(' ').toLowerCase(),
      };
    }).sort((x, y) => (y.date || '').localeCompare(x.date || ''));
  }

  function draw(rows) {
    list.innerHTML = rows.map(x => {
      const [who, extra, links] = x.html();
      return `<div class="row q"><div class="d">${sd(x.date)}</div><div class="t"><span class="ti">${esc(x.title)}</span>`
        + `<div class="sub">${who}</div>${extra ? `<div class="sub">${extra}</div>` : ''}<div class="go">${links}</div></div></div>`;
    }).join('');
  }

  function open(slug_, api) {
    kind = slug_;
    root.querySelectorAll('.qpanel').forEach(p => { p.hidden = p.dataset.kind !== slug_; });
    list.innerHTML = '<div class="empty">Wird geladen …</div>';
    api.unload();
    (cache[slug_] ??= fetch(`${slug_}.json`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }))
      .then(d => { if (kind === slug_) api.setRows(views(d), draw); })
      .catch(() => { list.innerHTML = '<div class="empty">Die Liste konnte nicht geladen werden.</div>'; });
  }

  // controls.js tells which kind is chosen (a button, a chart above, a link #liste=<kind>); load it once
  scope.addEventListener('controls:change', e => {
    const want = e.detail.state.f.liste?.[0];
    if (want && want !== kind) open(want, e.detail.api);
  });
  // a chart of the statistics chooses a list further down: show it
  scope.addEventListener('click', e => {
    if (e.target.closest('[data-static] [data-set]')) root.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  // the old link #liste opens the first kind
  if (location.hash === '#liste') addEventListener('DOMContentLoaded', () => root.querySelector('[data-f="liste"]')?.click());
})();
