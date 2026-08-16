/* Data Quality panel — a descriptive profile of the generated dataset.

   Self-contained: its own helpers and its own /api/quality fetch, with no
   dependency on app.js internals, so it composes cleanly and in isolation. The
   verdict (schema conformance + referential integrity) comes from the validator;
   the per-column profile (completeness, cardinality, spread, frequency) from the
   profiler. Marks are single-hue magnitude bars with direct labels — identity is
   never carried by colour. */
(function () {
  'use strict';

  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const fmt = n => (typeof n === 'number' ? n.toLocaleString('en-US') : esc(n));
  const num = v => (v == null ? '–' : (typeof v === 'number' ? v.toLocaleString('en-US', { maximumFractionDigits: 2 }) : esc(v)));
  const pct = (a, b) => (b ? Math.round((a / b) * 1000) / 10 : 0);

  let _cache = null;      // the fetched report, kept for re-opens
  let _overlay = null;

  // ── data fetch ─────────────────────────────────────────────────────────────
  function fetchQuality() {
    if (_cache) return Promise.resolve(_cache);
    return fetch('/api/quality')
      .then(r => r.json())
      .then(d => { _cache = d; return d; })
      .catch(() => ({ available: false, error: "Can't reach the DataPulse API. Make sure the server is running." }));
  }

  // ── column vizzes ────────────────────────────────────────────────────────────
  function completenessHtml(c) {
    const keptPct = Math.max(0, 100 - (c.null_pct || 0));
    const txt = c.nulls
      ? `${keptPct}% <span class="null">· ${c.null_pct}% null</span>`
      : '100%';
    return `<span class="q-complete" title="${c.count} of ${c.count + c.nulls} rows present">
      <span class="q-meter"><span class="q-meter-fill" style="width:${keptPct}%"></span></span>
      <span class="q-complete-txt">${txt}</span>
    </span>`;
  }

  function barsHtml(c) {
    const items = c.top || [];
    const maxC = items.reduce((m, d) => Math.max(m, d.count), 0) || 1;
    const rows = items.map(d => {
      const w = Math.max(2, Math.round((d.count / maxC) * 100));
      const share = pct(d.count, c.count);
      return `<div class="q-bar" title="${esc(d.value)}: ${fmt(d.count)} (${share}%)">
        <span class="q-bar-label">${esc(d.value)}</span>
        <span class="q-bar-track"><span class="q-bar-fill" style="width:${w}%"></span></span>
        <span class="q-bar-count">${fmt(d.count)}</span>
      </div>`;
    }).join('');
    const more = c.other ? `<div class="q-bar-more">+ ${fmt(c.other)} row(s) in ${Math.max(0, c.distinct - items.length)} other value(s)</div>` : '';
    const unused = (c.unused && c.unused.length)
      ? `<div class="q-unused">Declared but never generated: ${c.unused.map(v => `<code>${esc(v)}</code>`).join('')}</div>`
      : '';
    return `<div class="q-bars">${rows}</div>${more}${unused}`;
  }

  function numericHtml(c) {
    const stat = (label, v) => `<span><b>${label}</b> ${num(v)}</span>`;
    const line = `<div class="q-num-stats">
      ${stat('min', c.min)}${stat('p25', c.p25)}${stat('median', c.p50)}
      ${stat('mean', c.mean)}${stat('p75', c.p75)}${stat('max', c.max)}${stat('sd', c.std)}
    </div>`;
    const h = c.histogram;
    if (!h || !h.counts || !h.counts.length) return line;
    const maxC = h.counts.reduce((m, x) => Math.max(m, x), 0) || 1;
    const bars = h.counts.map((cnt, i) => {
      const ht = Math.max(2, Math.round((cnt / maxC) * 100));
      const lo = num(h.edges[i]), hi = num(h.edges[i + 1]);
      return `<span class="q-hist-bar${cnt ? '' : ' q-hist-empty'}" style="height:${ht}%" title="[${lo}, ${hi}): ${fmt(cnt)}"></span>`;
    }).join('');
    return `${line}<div class="q-hist">${bars}</div>
      <div class="q-hist-axis"><span>${num(h.edges[0])}</span><span>${num(h.edges[h.edges.length - 1])}</span></div>`;
  }

  function rangeHtml(c) {
    if (c.min == null) return `<div class="q-summary">no dated rows</div>`;
    return `<div class="q-range"><span>${esc(c.min)}</span><span class="arrow">→</span><span>${esc(c.max)}</span>
      <span class="span">· ${fmt(c.distinct)} distinct date(s)</span></div>`;
  }

  function summaryHtml(c) {
    if (c.role === 'key')       return `<div class="q-summary"><b>primary key</b> · ${fmt(c.distinct)} distinct · ${c.distinct_pct}% unique</div>`;
    if (c.role === 'reference') return `<div class="q-summary"><b>foreign key</b> · ${fmt(c.distinct)} distinct parent value(s) referenced</div>`;
    return `<div class="q-summary">${fmt(c.distinct)} distinct value(s) · ${c.distinct_pct}% unique</div>`;
  }

  function colViz(c) {
    if (c.role === 'numeric')  return numericHtml(c);
    if (c.role === 'datetime') return rangeHtml(c);
    if (c.top)                 return barsHtml(c);   // categorical or low-cardinality text
    return summaryHtml(c);
  }

  function colHtml(name, c) {
    const roleChip = ['key', 'reference'].includes(c.role) ? `<span class="q-chip role-${c.role}">${c.role === 'key' ? 'PK' : 'FK'}</span>` : '';
    return `<div class="q-col">
      <div class="q-col-head">
        <span class="q-cname">${esc(name)}</span>
        <span class="q-chip">${esc(c.type)}</span>
        ${roleChip}
        ${completenessHtml(c)}
      </div>
      ${colViz(c)}
    </div>`;
  }

  // ── table card (columns lazy-rendered on first expand) ───────────────────────
  function tableCard(name, t) {
    const el = document.createElement('div');
    el.className = 'q-table';
    el.dataset.name = name.toLowerCase();
    el.dataset.domain = String(t.domain || '').toLowerCase();
    el.innerHTML = `
      <button class="q-table-head">
        <span class="q-tchev">›</span>
        <span class="q-tname">${esc(name)}</span>
        <span class="q-trows">${fmt(t.row_count)} rows · ${t.column_count} cols</span>
      </button>
      <div class="q-tbody" hidden></div>`;
    const body = el.querySelector('.q-tbody');
    let rendered = false;
    el.querySelector('.q-table-head').addEventListener('click', () => {
      const open = el.classList.toggle('open');
      if (open && !rendered) {
        body.innerHTML = Object.entries(t.columns).map(([n, c]) => colHtml(n, c)).join('')
          || `<div class="q-empty">No columns profiled (table not generated).</div>`;
        rendered = true;
      }
      body.hidden = !open;
    });
    return el;
  }

  // ── overview + assembly ──────────────────────────────────────────────────────
  function tile(label, value, cls, note) {
    return `<div class="q-tile ${cls || ''}">
      <div class="q-tile-label">${esc(label)}</div>
      <div class="q-tile-value${String(value).length > 8 ? ' sm' : ''}">${value}</div>
      ${note ? `<div class="q-tile-note">${esc(note)}</div>` : ''}
    </div>`;
  }

  function renderReport(d) {
    const s = d.summary || {};
    const profile = d.profile || {};
    const totalCols = Object.values(profile).reduce((a, t) => a + (t.column_count || 0), 0);
    const clean = (s.violation_count || 0) === 0;
    const riPass = s.referential_integrity_pass !== false;

    const tiles = [
      tile('Tables', fmt(s.table_count || Object.keys(profile).length)),
      tile('Rows', fmt(s.total_rows || 0)),
      tile('Columns', fmt(totalCols)),
      tile('Violations', clean ? '0' : fmt(s.violation_count), clean ? 'good' : 'bad', clean ? 'schema + integrity clean' : 'schema / integrity'),
      tile('Ref. integrity', riPass ? 'Intact' : 'Issues', riPass ? 'good' : 'bad', 'every FK resolves'),
    ].join('');

    // Domain-grouped table cards (profile order already groups by domain).
    const groups = [];
    for (const [name, t] of Object.entries(profile)) {
      const dom = t.domain || 'Other';
      if (!groups.length || groups[groups.length - 1].domain !== dom) groups.push({ domain: dom, tables: [] });
      groups[groups.length - 1].tables.push([name, t]);
    }

    const body = _overlay.querySelector('.q-body');
    body.innerHTML = `
      <div class="q-tiles">${tiles}</div>
      <div class="q-note">Descriptive profile of the <b>synthetic data currently loaded</b>. The gate checks
        <b>schema conformance</b> and <b>referential integrity</b>; distributions are <b>described, not graded</b> —
        the generator declares no expected shapes, so there is no shape to grade against.</div>
      <div class="q-controls">
        <input class="q-search" type="text" placeholder="Filter tables by name or domain…" autocomplete="off" spellcheck="false" />
        <span class="q-controls-count"></span>
      </div>
      <div class="q-tables"></div>`;

    const host = body.querySelector('.q-tables');
    for (const g of groups) {
      const grp = document.createElement('div');
      grp.className = 'q-domain-group';
      grp.innerHTML = `<div class="q-domain-head">${esc(g.domain)} <span class="q-domain-count">${g.tables.length} table${g.tables.length !== 1 ? 's' : ''}</span></div>`;
      g.tables.forEach(([n, t]) => grp.appendChild(tableCard(n, t)));
      host.appendChild(grp);
    }

    // Header verdict + meta
    const verdict = _overlay.querySelector('.q-verdict');
    verdict.className = 'q-verdict ' + (clean ? 'pass' : 'fail');
    verdict.innerHTML = `<span class="q-verdict-dot"></span>${clean ? 'Passed all checks' : `${fmt(s.violation_count)} violation(s)`}`;
    const sub = _overlay.querySelector('.q-sub');
    sub.textContent = `${totalCols} columns profiled${s.generated_at ? ' · ' + s.generated_at : ''}${d.config_hash ? ' · ' + d.config_hash.slice(0, 17) : ''}`;

    // Live filter
    const search = body.querySelector('.q-search');
    const countEl = body.querySelector('.q-controls-count');
    const cards = Array.from(host.querySelectorAll('.q-table'));
    const totalTables = cards.length;
    const applyFilter = () => {
      const q = search.value.trim().toLowerCase();
      let shown = 0;
      cards.forEach(card => {
        const hit = !q || card.dataset.name.includes(q) || card.dataset.domain.includes(q);
        card.style.display = hit ? '' : 'none';
        if (hit) shown++;
      });
      host.querySelectorAll('.q-domain-group').forEach(g => {
        const any = Array.from(g.querySelectorAll('.q-table')).some(c => c.style.display !== 'none');
        g.style.display = any ? '' : 'none';
      });
      countEl.textContent = q ? `${shown} / ${totalTables} tables` : `${totalTables} tables`;
    };
    search.addEventListener('input', applyFilter);
    applyFilter();
  }

  function renderState(html, cls) {
    _overlay.querySelector('.q-body').innerHTML = `<div class="q-state ${cls || ''}">${html}</div>`;
    _overlay.querySelector('.q-verdict').innerHTML = '';
    _overlay.querySelector('.q-verdict').className = 'q-verdict';
    _overlay.querySelector('.q-sub').textContent = '';
  }

  // ── overlay lifecycle ────────────────────────────────────────────────────────
  function buildOverlay() {
    const el = document.createElement('div');
    el.id = 'quality-overlay';
    el.hidden = true;
    el.setAttribute('role', 'dialog');
    el.setAttribute('aria-modal', 'true');
    el.setAttribute('aria-label', 'Data quality report');
    el.innerHTML = `
      <div class="q-modal">
        <div class="q-head">
          <div class="q-title-wrap">
            <span class="eyebrow">Data Quality</span>
            <div class="q-title">Generated dataset profile</div>
            <div class="q-sub"></div>
            <span class="q-verdict"></span>
          </div>
          <button class="q-close" title="Close (Esc)" aria-label="Close">✕</button>
        </div>
        <div class="q-body"><div class="q-state">Loading profile…</div></div>
      </div>`;
    el.addEventListener('click', e => { if (e.target === el) close(); });
    el.querySelector('.q-close').addEventListener('click', close);
    document.body.appendChild(el);
    return el;
  }

  function open() {
    if (!_overlay) _overlay = buildOverlay();
    _overlay.hidden = false;
    _overlay.querySelector('.q-close').focus();
    renderState('Loading profile…');
    fetchQuality().then(d => {
      if (!d || d.available === false) {
        renderState(esc((d && d.error) || 'The data-quality report is unavailable.'), 'error');
      } else {
        renderReport(d);
      }
    });
  }

  function close() { if (_overlay) _overlay.hidden = true; }

  document.addEventListener('keydown', e => { if (e.key === 'Escape' && _overlay && !_overlay.hidden) close(); });

  function init() {
    const btn = document.getElementById('quality-btn');
    if (btn) btn.addEventListener('click', open);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
