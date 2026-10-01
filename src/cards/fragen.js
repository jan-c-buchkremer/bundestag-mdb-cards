// The research view of regierung/index.html (questions.py, docs/plan.md 12.5): every single question, one list per
// kind, each loaded from regierung/<kind>.json only when its tab is opened. Filters: words in the title, Fraktion,
// member, ministry, month, status, and for Kleine Anfragen the answer time. Every row links its sources (DIP, the
// PDF, the asker's card, and for oral questions the protocol and the speech page). No ranking: newest first.
'use strict';
(() => {
  const root = document.getElementById('fragen');
  if (!root) return;
  const $ = s => root.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  const norm = s => String(s ?? '').toLowerCase().replace(/ß/g, 'ss').normalize('NFD').replace(/[̀-ͯ]/g, '');
  const sd = d => d ? `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}` : '';
  const MONTHS = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  const monthLabel = m => `${MONTHS[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}`;
  const DIP_DOC = id => `https://dip.bundestag.de/drucksache/x/${encodeURIComponent(id)}`;
  const DIP_VORGANG = id => `https://dip.bundestag.de/vorgang/${encodeURIComponent(id)}`;
  // as data.drucksache_pdf: 21/6130 -> …/btd/21/061/2106130.pdf
  const pdfOf = number => { const [wp, n] = number.split('/'); const n5 = String(+n).padStart(5, '0'); return `https://dserver.bundestag.de/btd/${wp}/${n5.slice(0, 3)}/${wp}${n5}.pdf`; };
  const PAGE_ROWS = 50;
  const SHORT = { 'BÜNDNIS 90/DIE GRÜNEN': 'Grüne' };
  const cache = {};
  let kind = null, rows = [], shown = PAGE_ROWS;

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
  const speechHref = id => `../reden/${String(id).replace(/-\d+$/, '').replaceAll('/', '-')}.html`;
  const sittingHref = (sid, pos) => `../sitzungen/${sid.replaceAll('/', '-')}.html${pos != null ? `#top-${pos}` : ''}`;

  // one view per row: what the filters look at and what the list shows
  function views(d) {
    const k = d.kind;
    return d.rows.map(r => {
      if (k === 'kleine-anfragen') {
        const [doc, title, fractions, askers, ressort, answer, vorgang] = r;
        const date = d.docs[doc][2];
        const names = askers.map(i => d.persons[i]?.[1] || '');
        const days = answer ? answer[1] : null;
        return {
          date, title, fractions, names, ressort: d.ressorts[ressort] ?? null,
          status: answer ? 'beantwortet' : 'offen',
          time: days == null ? 'offen' : days <= 14 ? 'bis 14 Tage' : days <= 28 ? '15 bis 28 Tage' : 'mehr als 28 Tage',
          html: () => {
            const who = askers.slice(0, 3).map(i => person(d, i)).join(', ') + (askers.length > 3 ? ` und ${askers.length - 3} weitere` : '');
            const ans = answer ? `${docLinks(d, answer[0], 'Antwort')} nach ${days} Tagen` : '<span class="tag warn">noch keine Antwort im Datenbestand</span>';
            return [fractions.map(f => esc(SHORT[f] || f)).join(', ') + (who ? ` · ${who}` : ''), ans,
              [docLinks(d, doc, 'Anfrage'), vorgang ? a(DIP_VORGANG(vorgang), 'Vorgang im DIP') : ''].filter(Boolean).join(' · ')];
          },
        };
      }
      if (k === 'schriftliche-fragen' || k === 'muendliche-fragen') {
        const [vorgang, own, title, status, ressort, doc, asker, answer] = r;
        const date = own || (doc != null ? d.docs[doc][2] : '');
        const p = asker != null ? d.persons[asker] : null;
        return {
          date: date || '', title, fractions: p && p[2] ? [p[2]] : [], names: p ? [p[1]] : [], ressort: d.ressorts[ressort] ?? null,
          status: d.statuses[status] || 'ohne Stand',
          html: () => {
            const who = p ? person(d, asker) : doc != null ? '<span class="faint">Fragesteller:in: DIP nennt die Fragenden nur je Sammeldrucksache</span>' : '';
            const plenum = answer ? [answer[0] ? a(sittingHref(answer[0], answer[1]), `Antwort in der Fragestunde, Plenarprotokoll ${esc(answer[4])}${answer[2] ? `, S. ${esc(answer[2])}` : ''}`) : `Plenarprotokoll ${esc(answer[4])}${answer[2] ? `, S. ${esc(answer[2])}` : ''}`, answer[3] ? a(answer[3], 'Protokoll (PDF)') : ''].filter(Boolean).join(' · ') : '';
            return [[who, d.ressorts[ressort] ? esc(d.ressorts[ressort]) : ''].filter(Boolean).join(' · '), plenum,
              [a(DIP_VORGANG(vorgang), 'Frage im DIP'), doc != null ? docLinks(d, doc, 'Sammeldrucksache') : ''].filter(Boolean).join(' · ')];
          },
        };
      }
      const [speech, date, who, role, sitting, position, agenda, text] = r;
      const p = d.persons[who];
      return {
        date, title: text, fractions: !role && p && p[2] ? [p[2]] : [], names: p ? [p[1]] : [], ressort: role || null,
        status: role ? 'Antwort der Bundesregierung' : 'Frage',
        html: () => [`${person(d, who)}${role ? ` · ${esc(role)}` : ''}`, '',
          [a(speechHref(speech), 'Text im Protokoll'), sitting ? a(sittingHref(sitting, position), esc(agenda || 'Sitzung')) : ''].filter(Boolean).join(' · ')],
      };
    }).sort((x, y) => (y.date || '').localeCompare(x.date || ''));
  }

  function options(sel, values, all) {
    const cur = sel.value;
    sel.innerHTML = `<option value="">${all}</option>` + values.map(([v, label]) => `<option value="${esc(v)}">${esc(label)}</option>`).join('');
    sel.value = values.some(([v]) => v === cur) ? cur : '';
  }

  function setup(d) {
    rows = views(d);
    const count = f => [...new Set(rows.flatMap(f))].filter(Boolean).sort((x, y) => x.localeCompare(y, 'de'));
    options($('#ff'), count(r => r.fractions).map(f => [f, f]), 'alle Fraktionen');
    options($('#fr'), count(r => [r.ressort]).map(x => [x, x]), d.kind.startsWith('fragestunde') || d.kind === 'regierungsbefragung' ? 'jede Rolle' : 'alle Ressorts');
    options($('#fmo'), count(r => [r.date.slice(0, 7)]).reverse().map(m => [m, monthLabel(m)]), 'alle Monate');
    options($('#fs'), count(r => [r.status]).map(x => [x, x]), 'jeder Stand');
    $('#ft').hidden = d.kind !== 'kleine-anfragen';
    shown = PAGE_ROWS;
    render();
  }

  function filtered() {
    const words = norm($('#fq').value).split(/\s+/).filter(Boolean);
    const member = norm($('#fm').value.trim());
    const [f, r, m, st, t] = ['#ff', '#fr', '#fmo', '#fs', '#ft'].map(s => $(s).value);
    return rows.filter(x => (!words.length || words.every(w => norm(x.title).includes(w)))
      && (!member || x.names.some(n => norm(n).includes(member)))
      && (!f || x.fractions.includes(f)) && (!r || x.ressort === r) && (!m || x.date.startsWith(m))
      && (!st || x.status === st) && (!t || x.time === t));
  }

  function render() {
    const hits = filtered();
    $('#fcount').textContent = hits.length === rows.length ? `${rows.length.toLocaleString('de-DE')} ${rows.length === 1 ? 'Eintrag' : 'Einträge, die neuesten zuerst'}` : `${hits.length.toLocaleString('de-DE')} von ${rows.length.toLocaleString('de-DE')}`;
    $('#flist').innerHTML = hits.length ? hits.slice(0, shown).map(x => {
      const [who, extra, links] = x.html();
      return `<div class="row q"><div class="d">${sd(x.date)}</div><div class="t"><span class="ti">${esc(x.title)}</span>`
        + `<div class="sub">${who}</div>${extra ? `<div class="sub">${extra}</div>` : ''}<div class="go">${links}</div></div></div>`;
    }).join('') : '<div class="empty">Keine Treffer.</div>';
    $('#fmore').style.display = hits.length > shown ? '' : 'none';  // .more sets its own display
  }

  function open(slug) {
    kind = slug;
    root.querySelectorAll('.qtabs button').forEach(b => b.setAttribute('aria-selected', b.dataset.k === slug));
    $('#flist').innerHTML = '<div class="empty">Wird geladen …</div>';
    (cache[slug] ??= fetch(`${slug}.json`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }))
      .then(d => { if (kind === slug) setup(d); })
      .catch(() => { $('#flist').innerHTML = '<div class="empty">Die Liste konnte nicht geladen werden.</div>'; });
    history.replaceState(null, '', `#liste=${slug}`);
  }

  root.querySelector('.qtabs').addEventListener('click', e => { const b = e.target.closest('button[data-k]'); if (b) open(b.dataset.k); });
  for (const s of ['#fq', '#fm']) $(s).addEventListener('input', () => { shown = PAGE_ROWS; render(); });
  for (const s of ['#ff', '#fr', '#fmo', '#fs', '#ft']) $(s).addEventListener('change', () => { shown = PAGE_ROWS; render(); });
  $('#fmore').addEventListener('click', () => { shown += PAGE_ROWS; render(); });
  const want = new URLSearchParams(location.hash.slice(1)).get('liste');
  const first = root.querySelector(`.qtabs button[data-k="${want}"]`) || root.querySelector('.qtabs button');
  // the list loads only when asked for: a tab, or a link to it
  if (want || location.hash === '#liste') open(first.dataset.k);
  else $('#flist').innerHTML = '<div class="empty">Eine Art oben wählen: Die Liste wird erst dann geladen.</div>';
})();
