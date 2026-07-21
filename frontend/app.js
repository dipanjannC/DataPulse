(function () {
  'use strict';

  // ── Constants ──────────────────────────────────────────────────────────────
  const SUGGESTIONS = [
    { label: 'Sales',     text: 'Show top 5 customers by total revenue' },
    { label: 'IT',        text: 'High-priority IT incidents this month' },
    { label: 'HR',        text: 'Employees with the most leave days remaining' },
    { label: 'Marketing', text: 'Marketing campaigns with the highest ROI' },
    { label: 'Security',  text: 'Most common security vulnerabilities detected' },
    { label: 'HR',        text: 'Payroll distribution across all departments' },
  ];
  const LOG_CFG = {
    info:  { color: '#6B6B78', prefix: 'SYS' },
    embed: { color: '#8A8A96', prefix: 'EMB' },
    kg:    { color: '#8A8A96', prefix: 'KG ' },
    llm:   { color: '#8A8A96', prefix: 'LLM' },
    sql:   { color: '#8A8A96', prefix: 'SQL' },
    db:    { color: '#8A8A96', prefix: 'DB ' },
    done:  { color: '#A100FF', prefix: 'OK ' },
    error: { color: '#FF5C5C', prefix: 'ERR' },
  };
  const PAGE_SIZE = 50;

  // ── Utilities ──────────────────────────────────────────────────────────────
  const esc   = s => String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const now   = () => new Date().toLocaleTimeString('en-US', { hour12:false, hour:'2-digit', minute:'2-digit', second:'2-digit' });
  const delay = ms => new Promise(r => setTimeout(r, ms));

  // ── SQL Tokenizer ──────────────────────────────────────────────────────────
  const KW = new Set(['SELECT','FROM','WHERE','JOIN','INNER','LEFT','RIGHT','OUTER','FULL','ON','GROUP','BY','ORDER','HAVING','LIMIT','OFFSET','AS','AND','OR','NOT','IN','LIKE','BETWEEN','IS','NULL','DISTINCT','WITH','UNION','ALL','INTERSECT','EXCEPT','CASE','WHEN','THEN','ELSE','END','INSERT','INTO','VALUES','UPDATE','SET','DELETE','CREATE','DROP','ALTER','TABLE','ASC','DESC','EXISTS','OVER','PARTITION','ROWS','RANGE','RECURSIVE','CROSS']);
  const FN  = new Set(['COUNT','SUM','AVG','MAX','MIN','COALESCE','CAST','ROUND','ABS','UPPER','LOWER','TRIM','LENGTH','SUBSTR','REPLACE','IFNULL','NULLIF','IIF','STRFTIME','DATE','DATETIME','JULIANDAY','TYPEOF','ROW_NUMBER','RANK','DENSE_RANK','LAG','LEAD','FIRST_VALUE','LAST_VALUE']);
  const SQL_C = { kw:'var(--sql-kw)', fn:'var(--sql-fn)', str:'var(--sql-str)', num:'var(--sql-num)', comment:'var(--sql-cmt)', op:'var(--sql-op)', id:'var(--text)', pt:'var(--sql-pt)' };

  function tokenize(sql) {
    const out = []; let i = 0;
    while (i < sql.length) {
      if (/\s/.test(sql[i]))            { let j=i; while(j<sql.length&&/\s/.test(sql[j]))j++;    out.push({t:'ws',v:sql.slice(i,j)}); i=j; continue; }
      if (sql[i]==='-'&&sql[i+1]==='-') { let j=i; while(j<sql.length&&sql[j]!=='\n')j++;       out.push({t:'comment',v:sql.slice(i,j)}); i=j; continue; }
      if (sql[i]==="'")                 { let j=i+1; while(j<sql.length&&sql[j]!=="'")j++;       out.push({t:'str',v:sql.slice(i,j+1)}); i=j+1; continue; }
      if (/\d/.test(sql[i]))            { let j=i; while(j<sql.length&&/[\d.]/.test(sql[j]))j++; out.push({t:'num',v:sql.slice(i,j)}); i=j; continue; }
      if (/[a-zA-Z_]/.test(sql[i]))     { let j=i; while(j<sql.length&&/\w/.test(sql[j]))j++;   const w=sql.slice(i,j),u=w.toUpperCase(); out.push({t:KW.has(u)?'kw':FN.has(u)?'fn':'id',v:w}); i=j; continue; }
      if (/[=<>!*]/.test(sql[i]))       { let j=i; while(j<sql.length&&/[=<>!*]/.test(sql[j]))j++; out.push({t:'op',v:sql.slice(i,j)}); i=j; continue; }
      out.push({t:'pt',v:sql[i]}); i++;
    }
    return out;
  }
  function highlightSQL(sql) {
    return tokenize(sql).map(({t,v}) => { const c=SQL_C[t]; return c?`<span style="color:${c}">${esc(v)}</span>`:esc(v); }).join('');
  }

  // ── Pipeline Card (the signature) ────────────────────────────────────────────
  // Five honest stages that mirror the real backend flow:
  //   retrieve_schema_context → generate_sql (with retries) → SQLite execution.
  // No fabricated per-step timings or infra claims; only real details are shown
  // (matched tables/domains, attempts, row count) plus the true total elapsed.
  const PIPELINE_STEPS = [
    { label: 'Understanding your question' },
    { label: 'Searching the knowledge graph' },
    { label: 'Assembling schema context' },
    { label: 'Generating SQL' },
    { label: 'Running the query' },
  ];

  class PipelineCard {
    constructor(question) {
      this._q        = question;
      this._status   = PIPELINE_STEPS.map(() => 'pending');
      this._detail   = PIPELINE_STEPS.map(() => '');
      this._total    = null;
      this._collapsed = false;
      this._el       = this._build();
      this._renderSteps();
    }

    activate(i)  { this._status[i] = 'active';  this._renderSteps(); }

    complete(i, detail) {
      this._status[i] = 'done';
      if (detail != null) this._detail[i] = detail;
      this._renderSteps();
    }

    fail(i, detail) {
      this._status[i] = 'error';
      if (detail) this._detail[i] = detail;
      this._el.classList.add('has-error');
      this._renderSteps();
    }

    updateDetail(i, detail) {
      this._detail[i] = detail;
      this._renderSteps();
    }

    setTotal(ms) {
      this._total = ms;
      const t = this._el.querySelector('.pipeline-total');
      if (t) t.textContent = `${(ms / 1000).toFixed(2)}s`;
      this._el.classList.add('all-done');
    }

    get el() { return this._el; }

    _icon(st) {
      return { pending:'>', active:'>', done:'✓', error:'✗' }[st] || '>';
    }

    _renderSteps() {
      const body = this._el.querySelector('.pipeline-steps');
      body.innerHTML = PIPELINE_STEPS.map((s, i) => {
        const st  = this._status[i];
        const det = this._detail[i];
        const right = st === 'active' ? `<span class="step-spinner"></span>` : '';
        return `<div class="pipeline-step ${st}">
          <span class="step-icon">${this._icon(st)}</span>
          <span class="step-body">
            <span class="step-label">${esc(s.label)}</span>
            ${det ? `<span class="step-detail">${esc(det)}</span>` : ''}
          </span>
          ${right}
        </div>`;
      }).join('');
    }

    _build() {
      const el = document.createElement('div');
      el.className = 'pipeline-card';
      const qShort = this._q.length > 55 ? this._q.slice(0,55) + '…' : this._q;
      el.innerHTML = `
        <div class="pipeline-header">
          <div class="pipeline-title-row">
            <span class="pipeline-badge">Query Pipeline</span>
            <span class="pipeline-qtext">${esc(qShort)}</span>
          </div>
          <div class="pipeline-right">
            <span class="pipeline-total"></span>
            <button class="pipeline-toggle" title="Toggle">▾</button>
          </div>
        </div>
        <div class="pipeline-steps"></div>
      `;
      el.querySelector('.pipeline-toggle').addEventListener('click', e => {
        e.stopPropagation();
        this._collapsed = !this._collapsed;
        el.classList.toggle('collapsed', this._collapsed);
        el.querySelector('.pipeline-toggle').textContent = this._collapsed ? '▸' : '▾';
      });
      return el;
    }
  }

  // ── System log ───────────────────────────────────────────────────────────────
  function simLog(msg, type) {
    type = type || 'info';
    const list = document.getElementById('log-list');
    if (!list) return;
    const cfg = LOG_CFG[type] || LOG_CFG.info;
    const el  = document.createElement('div');
    el.className = `log-entry log-${type}`;
    el.innerHTML = `<span class="log-time">${now()}</span><span class="log-prefix" style="color:${cfg.color}">${cfg.prefix}</span><span class="log-msg">${esc(msg)}</span>`;
    list.appendChild(el);
    while (list.children.length > 24) list.removeChild(list.firstChild);
    list.scrollTop = list.scrollHeight;
  }

  // ── API ────────────────────────────────────────────────────────────────────
  const api = {
    health:  ()           => fetch('/api/health').then(r => r.json()),
    domains: ()           => fetch('/api/domains').then(r => r.json()),
    query:   (q, k)       => fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, top_k: k || 10 }),
    }).then(r => r.json()),
  };

  // ── Typewriter SQL ─────────────────────────────────────────────────────────
  function typewriterSQL(pre, sql) {
    const total = sql.length;
    const spd   = Math.max(4, Math.ceil(total / 70));
    let pos = 0;
    (function tick() {
      pos = Math.min(pos+spd, total);
      pre.innerHTML = highlightSQL(sql.slice(0,pos)) + (pos<total?'<span class="tw-cursor">▊</span>':'');
      if (pos < total) requestAnimationFrame(tick);
    })();
  }

  // ── DOM Builders ───────────────────────────────────────────────────────────
  function buildUserBubble(text) {
    const el = document.createElement('div');
    el.className = 'msg-user';
    el.innerHTML = `<div class="msg-user-bubble">${esc(text)}</div>`;
    return el;
  }

  function buildDomainBadges(tables) {
    const domains = [...new Set(Object.values(tables).map(t => t.domain).filter(Boolean))];
    if (!domains.length) return null;
    const el = document.createElement('div');
    el.className = 'domain-badges';
    el.innerHTML = domains.map(d => {
      return `<span class="domain-badge">${esc(d)}</span>`;
    }).join('');
    return el;
  }

  function buildSchemaToggle(tables) {
    const names = Object.keys(tables);
    const el    = document.createElement('div');
    el.className = 'schema-toggle';
    let open = false;
    function render() {
      el.innerHTML = `
        <button class="schema-header">
          <span><span class="schema-icon">&gt;</span>Schema Context · ${names.length} table${names.length!==1?'s':''}</span>
          <span class="schema-arrow" style="transform:rotate(${open?'180':'0'}deg)">▾</span>
        </button>
        ${open?`<div class="schema-body">${names.map(n=>`<span class="table-pill" title="${esc(tables[n]?.description||n)}">${esc(n)}</span>`).join('')}</div>`:''}
      `;
      el.querySelector('.schema-header').addEventListener('click', () => { open=!open; render(); });
    }
    render();
    return el;
  }

  function buildSQLBlock(sql) {
    const el = document.createElement('div');
    el.className = 'sql-block';
    el.innerHTML = `
      <div class="sql-bar">
        <span class="sql-label">Generated SQL</span>
        <button class="copy-btn">⎘ copy</button>
      </div>
      <pre class="sql-pre"></pre>
    `;
    const pre = el.querySelector('.sql-pre');
    const btn = el.querySelector('.copy-btn');
    typewriterSQL(pre, sql);
    btn.addEventListener('click', () => {
      navigator.clipboard.writeText(sql).then(() => {
        btn.textContent = '✓ copied'; btn.classList.add('copied');
        setTimeout(() => { btn.textContent = '⎘ copy'; btn.classList.remove('copied'); }, 2200);
      });
    });
    return el;
  }

  function buildResultsTable(columns, rows) {
    const el    = document.createElement('div');
    el.className = 'results-table';
    let page    = 0;
    const pages = Math.ceil(rows.length / PAGE_SIZE);
    function render() {
      const sl = rows.slice(page*PAGE_SIZE, (page+1)*PAGE_SIZE);
      el.innerHTML = `
        <div class="results-bar">
          <span class="results-label">Query Results</span>
          <span class="results-count">${rows.length.toLocaleString()} row${rows.length!==1?'s':''} · ${columns.length} col${columns.length!==1?'s':''}</span>
        </div>
        <div class="results-scroll">
          <table>
            <thead><tr>${columns.map(c=>`<th>${esc(c)}</th>`).join('')}</tr></thead>
            <tbody>${sl.map((row,i)=>`<tr class="${i%2===1?'alt':''}">${row.map(cell=>
              `<td>${cell===null?'<span class="null-val">null</span>':esc(String(cell))}</td>`
            ).join('')}</tr>`).join('')}</tbody>
          </table>
        </div>
        ${pages>1?`<div class="pagination">
          <button class="page-btn prev-btn"${page===0?' disabled':''}>←</button>
          <span>${page+1} / ${pages}</span>
          <button class="page-btn next-btn"${page===pages-1?' disabled':''}>→</button>
        </div>`:''}
      `;
      const prev=el.querySelector('.prev-btn'), next=el.querySelector('.next-btn');
      if (prev) prev.addEventListener('click', () => { page--; render(); });
      if (next) next.addEventListener('click', () => { page++; render(); });
    }
    render();
    return el;
  }

  function buildAssistantBubble(data) {
    const wrapper = document.createElement('div');
    wrapper.className = 'msg-assistant';
    const tables = (data.schema_context && data.schema_context.tables) || {};

    const badges = buildDomainBadges(tables);
    if (badges) wrapper.appendChild(badges);

    if (!data.success) {
      const err = document.createElement('div');
      err.className = 'msg-error';
      err.innerHTML = `
        <div class="error-title">Query failed</div>
        <div class="error-body">${esc(data.error||data.detail||'Unknown error')}</div>
        ${data.sql?`<div class="error-sql">${esc(data.sql)}</div>`:''}
      `;
      wrapper.appendChild(err);
      return wrapper;
    }

    if (Object.keys(tables).length > 0) wrapper.appendChild(buildSchemaToggle(tables));
    if (data.sql) wrapper.appendChild(buildSQLBlock(data.sql));
    if (data.columns && data.columns.length > 0) {
      wrapper.appendChild(buildResultsTable(data.columns, data.rows || []));
    }
    return wrapper;
  }

  // ── Sidebar ────────────────────────────────────────────────────────────────
  function setKGStatus(status) {
    const dot = document.getElementById('kg-dot'), lbl = document.getElementById('kg-label');
    dot.className = 'kg-dot ' + status;
    const labels = { connected:'Online', connecting:'Connecting…', error:'Offline' };
    lbl.textContent = labels[status] || status;
    if (status === 'connected') simLog('Backend online', 'done');
    else if (status === 'error') simLog('Backend offline', 'error');
  }

  function setDomains(domains) {
    document.getElementById('domains-list').innerHTML = domains.map(d => {
      const key   = String(d.name || '').toUpperCase();
      const label = key.length <= 3 ? key : key[0] + key.slice(1).toLowerCase();  // keep acronyms (IT, HR) uppercase
      return `<div class="domain-item" title="${esc(d.description||d.name)}">
        <span class="domain-dot"></span>
        <span class="domain-name">${esc(label)}</span>
      </div>`;
    }).join('');
    const countEl = document.getElementById('domain-count');
    if (countEl) countEl.textContent = `${domains.length} domain${domains.length !== 1 ? 's' : ''}`;
    simLog(`Loaded ${domains.length} domains from knowledge graph`, 'kg');
  }

  const EMPTY_RECENT_HTML = `<div class="empty-recent">
    <svg class="empty-recent-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.4" stroke-dasharray="3 2.2"/>
      <path d="M12 8v4.25l2.75 2.75" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    <p class="empty-recent-primary">No recent queries</p>
    <p class="empty-recent-secondary">Ask a question — click any entry here to replay it</p>
  </div>`;

  const sidebarRecent = [];
  function addRecent(text) {
    const idx = sidebarRecent.indexOf(text);
    if (idx > -1) sidebarRecent.splice(idx,1);
    sidebarRecent.unshift(text);
    if (sidebarRecent.length > 8) sidebarRecent.pop();
    const list = document.getElementById('recent-list');
    list.innerHTML = sidebarRecent
      .map(t => `<button class="recent-item" data-q="${esc(t)}">${esc(t)}</button>`)
      .join('');
    list.querySelectorAll('.recent-item').forEach(btn => btn.addEventListener('click', () => sendQuery(btn.dataset.q)));
    document.getElementById('clear-btn').style.display = '';
  }

  // ── Empty State ────────────────────────────────────────────────────────────
  function showEmpty() {
    const msgs = document.getElementById('messages');
    if (msgs.querySelector('#empty-state')) return;
    const es = document.createElement('div');
    es.id = 'empty-state';
    es.innerHTML = `
      <div class="empty-hero">
        <div class="empty-eyebrow"><span class="eyebrow">Sales · IT · HR · Marketing · Security</span></div>
        <div class="empty-logo-row">
          <svg class="empty-logo-icon" width="46" height="46" viewBox="0 0 30 30" fill="none" aria-hidden="true">
            <path d="M8 5 L20 15 L8 25" stroke="#A100FF" stroke-width="4" stroke-linecap="square" stroke-linejoin="miter"/>
          </svg>
          <div class="empty-name">DataPulse</div>
        </div>
        <div class="empty-pills">
          <span class="empty-pill">5 domains</span>
          <span class="empty-pill">50 tables</span>
          <span class="empty-pill">373 embedded columns</span>
        </div>
      </div>

      <div class="highlighted-caption">
        Ask about your enterprise data in plain English.
        <span class="hl-brand">DataPulse</span> searches its knowledge graph for the right schema and writes the query for you — no SQL required.
      </div>

      <div class="suggestions-grid">
        ${SUGGESTIONS.map(s => `
          <button class="suggestion-card" data-q="${esc(s.text)}">
            <span class="suggestion-label">${esc(s.label)}</span>${esc(s.text)}
          </button>`).join('')}
      </div>
    `;
    es.querySelectorAll('.suggestion-card').forEach(btn => btn.addEventListener('click', () => sendQuery(btn.dataset.q)));
    msgs.appendChild(es);
  }

  function scrollBottom() {
    const win = document.getElementById('chat-window');
    setTimeout(() => win.scrollTo({ top: win.scrollHeight, behavior: 'smooth' }), 60);
  }

  // ── Input ──────────────────────────────────────────────────────────────────
  function initInput() {
    const ta  = document.getElementById('query-input');
    const btn = document.getElementById('send-btn');
    const gl  = document.getElementById('prompt-glyph');

    function syncState() {
      const ready = !!ta.value.trim() && !_busy;
      btn.className = ready ? 'ready' : '';
      gl.className  = 'prompt-glyph' + (_busy ? ' loading' : '');
    }

    ta.addEventListener('input', () => {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
      syncState();
    });
    ta.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); }
    });
    btn.addEventListener('click', submit);

    document.getElementById('clear-btn').addEventListener('click', () => {
      sidebarRecent.length = 0;
      document.getElementById('recent-list').innerHTML = EMPTY_RECENT_HTML;
      document.getElementById('clear-btn').style.display = 'none';
    });

    function submit() {
      const q = ta.value.trim();
      if (!q || _busy) return;
      ta.value = ''; ta.style.height = 'auto'; syncState();
      sendQuery(q);
    }
  }

  // ── Main Query Pipeline ────────────────────────────────────────────────────
  let _busy = false, _queryCount = 0;

  async function sendQuery(question) {
    if (_busy) return;
    _busy = true;
    try { await _runQuery(question); } catch(e) { console.error('sendQuery error:', e); simLog(`Internal error: ${e.message}`, 'error'); }
    _busy = false;
    document.getElementById('prompt-glyph').className = 'prompt-glyph';
    if (document.getElementById('query-input').value.trim()) document.getElementById('send-btn').className = 'ready';
  }

  async function _runQuery(question) {
    _queryCount++;

    const counter = document.getElementById('query-counter');
    if (counter) counter.textContent = `${_queryCount} ${_queryCount===1?'query':'queries'}`;

    document.getElementById('prompt-glyph').className = 'prompt-glyph loading';
    document.getElementById('send-btn').className = '';

    const es = document.getElementById('empty-state');
    if (es) es.remove();

    const msgs = document.getElementById('messages');
    msgs.appendChild(buildUserBubble(question));

    const card = new PipelineCard(question);
    msgs.appendChild(card.el);
    scrollBottom();
    addRecent(question);

    simLog(`Query: "${question.slice(0,42)}${question.length>42?'…':''}"`, 'info');

    // One real API call does all server-side work: schema retrieval, SQL
    // generation (with retries), and SQLite execution. The client can't observe
    // the server-side stage boundaries, so no step is marked done until the call
    // returns: the active step holds while we wait, then we advance only as far
    // as the real outcome confirms. Only real details are ever shown, and a step
    // is never checked green above a step that errored.
    const apiPromise = api.query(question)
      .catch(err => ({ success: false, error: err.message, sql: '', schema_context: {}, columns: [], rows: [] }));

    const t0 = performance.now();
    const reveal = 160;

    // Stage 0 — the app has received the question (client-side, genuinely done).
    card.activate(0);
    await delay(reveal);
    card.complete(0);

    // Stage 1 — schema retrieval (embed + KG vector search + FK expansion). Holds
    // active across the real wait; any no-SQL failure is a retrieval failure and
    // lands here, leaving the later steps pending.
    card.activate(1);
    simLog('Searching knowledge graph for relevant schema', 'kg');

    const data = await apiPromise;

    const tables   = Object.keys(data.schema_context && data.schema_context.tables ? data.schema_context.tables : {});
    const domains  = [...new Set(tables.map(n => data.schema_context.tables[n] && data.schema_context.tables[n].domain).filter(Boolean))];
    const kgDetail = tables.length ? `${tables.length} table${tables.length!==1?'s':''}${domains.length?` · ${domains.slice(0,3).join(', ')}`:''}` : '';

    if (!data.success && !data.sql) {
      // Failed before any SQL was produced → the retrieval step is what broke.
      card.fail(1, (data.error||data.detail||'error').slice(0,80));
      simLog(`Failed: ${(data.error||data.detail||'').slice(0,60)}`, 'error');
    } else {
      // Retrieval returned (we have schema and/or generated SQL). Advance the
      // confirmed stages — the checks appear only now.
      card.complete(1, kgDetail);
      if (tables.length) simLog(`Matched ${tables.length} table${tables.length!==1?'s':''}${domains.length?` across ${domains.length} domain${domains.length!==1?'s':''}`:''}`, 'kg');

      card.activate(2);
      await delay(reveal);
      card.complete(2);

      const attempts = data.attempts || 1;
      card.activate(3);
      simLog('Generating SQL with LLaMA-3.3-70b via Groq', 'llm');
      await delay(reveal);
      card.complete(3, `${attempts} attempt${attempts!==1?'s':''}`);
      simLog(`SQL generated (${attempts} attempt${attempts!==1?'s':''})`, 'llm');

      card.activate(4);
      await delay(reveal);
      if (data.success) {
        const rowCount = data.rows ? data.rows.length : 0;
        card.complete(4, `${rowCount.toLocaleString()} row${rowCount!==1?'s':''}`);
        const elapsed = Math.round(performance.now() - t0);
        simLog(`Done — ${rowCount} row${rowCount!==1?'s':''} in ${(elapsed/1000).toFixed(2)}s`, 'done');
      } else {
        // SQL was produced but the query did not execute cleanly.
        card.fail(4, (data.error||data.detail||'error').slice(0,80));
        simLog(`Failed: ${(data.error||data.detail||'').slice(0,60)}`, 'error');
      }
    }

    card.setTotal(Math.round(performance.now() - t0));
    msgs.appendChild(buildAssistantBubble(data));
    scrollBottom();
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  async function init() {
    initInput();
    showEmpty();
    simLog('DataPulse ready', 'info');

    api.health()
      .then(h => setKGStatus(h.status === 'ok' ? 'connected' : 'error'))
      .catch(() => setKGStatus('error'));

    api.domains()
      .then(d => setDomains(d.domains || []))
      .catch(() => {});
  }

  document.addEventListener('DOMContentLoaded', init);
})();
