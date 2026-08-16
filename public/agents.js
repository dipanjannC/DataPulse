(function () {
  'use strict';

  // ── Agent registry ────────────────────────────────────────────────────────
  const AGENTS = [
    {
      id:    'LEXIS',
      role:  'NL Interpreter',
      icon:  '◈',
      color: '#A100FF',
      desc:  'Parses the question — extracts intent, entities, filters, and sort order.',
      summaryFn: r => [
        ['Intent',   r.intent        || '—'],
        ['Metric',   r.primary_metric || '—'],
        ['Entities', (r.entities || []).slice(0,3).join(', ') || '—'],
        ['Filters',  (r.filters  || []).slice(0,2).join(', ') || 'none'],
        ['Time',     r.time_reference || 'none'],
      ],
    },
    {
      id:    'GRAPHOS',
      role:  'KG Search Agent',
      icon:  '◉',
      color: '#7EC8FF',
      desc:  'Vector-searches the Neo4j knowledge graph to find relevant tables and join paths.',
      summaryFn: r => [
        ['Tables',   (r.tables_found  || []).length + ' found'],
        ['Domains',  (r.domains_found || []).map(d => d.name).slice(0,3).join(', ') || '—'],
        ['Joins',    (r.joins_found   || []).length + ' paths'],
        ['Metrics',  (r.metrics_found || []).length + ' defined'],
        ['X-domain', r.cross_domain_unjoinable ? '⚠ unjoinable' : 'ok'],
      ],
    },
    {
      id:    'SCOUT',
      role:  'Schema Discovery',
      icon:  '◎',
      color: '#BE82FF',
      desc:  'Maps every table and column found in the KG to concrete SQLite schema metadata.',
      summaryFn: r => {
        const dd = r.domain_breakdown || {};
        const domainStr = Object.entries(dd).map(([d,t])=>`${d}(${t.length})`).slice(0,3).join(', ');
        return [
          ['Tables',   (r.tables_mapped || []).length + ' mapped'],
          ['Columns',  r.total_columns + ' discovered'],
          ['Domains',  domainStr || '—'],
          ['Joins',    r.joins_available + ' available'],
          ['Coverage', Math.round((r.coverage_score||0)*100) + '%'],
        ];
      },
    },
    {
      id:    'FORGE',
      role:  'SQL Writer',
      icon:  '◆',
      color: '#7DD6C0',
      desc:  'Drafts a SQLite-compatible SELECT query from the schema context.',
      summaryFn: r => [
        ['Generated', r.generated ? 'yes' : 'no'],
        ['Complexity', r.complexity || '—'],
        ['Lines',   r.sql ? r.sql.split('\n').length + ' lines' : '0'],
      ],
    },
    {
      id:    'SENTINEL',
      role:  'SQL Validator',
      icon:  '◈',
      color: '#F0A868',
      desc:  'Checks the query for safety, syntax, and schema alignment before execution.',
      summaryFn: r => {
        const checks = r.checks || {};
        return [
          ['Safety',    checks.safety    ? '✓ pass' : '✗ fail'],
          ['Syntax',    checks.syntax    ? '✓ pass' : '✗ fail'],
          ['Structure', checks.structure ? '✓ pass' : '✗ fail'],
          ['Tables',    checks.tables    ? '✓ pass' : '⚠ warn'],
          ['Issues',    (r.issues||[]).length > 0 ? (r.issues||[]).join('; ').slice(0,40) : 'none'],
        ];
      },
    },
    {
      id:    'ORACLE',
      role:  'Executor & NL Agent',
      icon:  '◉',
      color: '#FF82C0',
      desc:  'Runs the validated SQL and translates the raw result into plain English.',
      summaryFn: r => [
        ['Executed', r.executed ? 'yes' : 'no'],
        ['Rows',     r.row_count + ' returned'],
        ['Columns',  (r.columns||[]).length + ' cols'],
        ['Grounded', r.grounded ? 'yes' : 'no'],
      ],
    },
  ];

  // ── Suggestion chips ──────────────────────────────────────────────────────
  const CHIPS = [
    'Show top 5 customers by total revenue',
    'High-priority IT incidents this month',
    'Employees with most leave days remaining',
    'Marketing campaigns with the highest ROI',
    'Most common security vulnerabilities detected',
    'Payroll distribution across departments',
  ];

  // ── SQL Tokenizer (same as app.js) ────────────────────────────────────────
  const KW = new Set(['SELECT','FROM','WHERE','JOIN','INNER','LEFT','RIGHT','OUTER','ON','GROUP','BY','ORDER','HAVING','LIMIT','OFFSET','AS','AND','OR','NOT','IN','LIKE','BETWEEN','IS','NULL','DISTINCT','WITH','UNION','ALL','CASE','WHEN','THEN','ELSE','END','OVER','PARTITION','ASC','DESC','RECURSIVE','CROSS']);
  const FN = new Set(['COUNT','SUM','AVG','MAX','MIN','COALESCE','CAST','ROUND','ABS','UPPER','LOWER','TRIM','LENGTH','SUBSTR','REPLACE','IFNULL','NULLIF','STRFTIME','DATE','DATETIME','ROW_NUMBER','RANK','DENSE_RANK','LAG','LEAD']);

  function highlightSQL(sql) {
    const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const tokens = [];
    let i = 0;
    while (i < sql.length) {
      if (/\s/.test(sql[i]))            { let j=i; while(j<sql.length&&/\s/.test(sql[j]))j++; tokens.push({t:'ws',v:sql.slice(i,j)}); i=j; continue; }
      if (sql[i]==='-'&&sql[i+1]==='-') { let j=i; while(j<sql.length&&sql[j]!=='\n')j++; tokens.push({t:'cmt',v:sql.slice(i,j)}); i=j; continue; }
      if (sql[i]==="'")                 { let j=i+1; while(j<sql.length&&sql[j]!=="'")j++; tokens.push({t:'str',v:sql.slice(i,j+1)}); i=j+1; continue; }
      if (/\d/.test(sql[i]))            { let j=i; while(j<sql.length&&/[\d.]/.test(sql[j]))j++; tokens.push({t:'num',v:sql.slice(i,j)}); i=j; continue; }
      if (/[a-zA-Z_]/.test(sql[i]))     { let j=i; while(j<sql.length&&/\w/.test(sql[j]))j++; const w=sql.slice(i,j),u=w.toUpperCase(); tokens.push({t:KW.has(u)?'kw':FN.has(u)?'fn':'id',v:w}); i=j; continue; }
      if (/[=<>!*]/.test(sql[i]))       { let j=i; while(j<sql.length&&/[=<>!*]/.test(sql[j]))j++; tokens.push({t:'op',v:sql.slice(i,j)}); i=j; continue; }
      tokens.push({t:'pt',v:sql[i]}); i++;
    }
    const cls = {kw:'sql-kw',fn:'sql-fn',str:'sql-str',num:'sql-num',cmt:'sql-cmt',op:'sql-op'};
    return tokens.map(({t,v})=>cls[t]?`<span class="${cls[t]}">${esc(v)}</span>`:esc(v)).join('');
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  const esc   = s => String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const $     = id => document.getElementById(id);
  const delay = ms => new Promise(r => setTimeout(r, ms));

  // ── DOM references ─────────────────────────────────────────────────────────
  let questionInput, runBtn, chipsContainer;
  let flowNodes, flowArrows;
  let agentCards = {};           // keyed by agent id
  let summaryBar, resultPanel;
  let answerEl, sqlCodeEl, tableWrapEl, rowCountEl;

  // ── Build the page ─────────────────────────────────────────────────────────

  function buildPage() {
    questionInput  = $('question-input');
    runBtn         = $('run-btn');
    chipsContainer = $('chips');
    summaryBar     = $('summary-bar');
    resultPanel    = $('result-panel');
    answerEl       = $('answer-text');
    sqlCodeEl      = $('sql-code');
    tableWrapEl    = $('table-wrap');
    rowCountEl     = $('row-count-badge');

    // Flow nodes and arrows
    flowNodes  = {};
    flowArrows = [];
    AGENTS.forEach((a, i) => {
      flowNodes[a.id]  = $('flow-dot-'  + a.id);
      if (i < AGENTS.length - 1) {
        flowArrows.push($('flow-arrow-' + i));
      }
    });

    // Agent card refs
    AGENTS.forEach(a => {
      agentCards[a.id] = {
        card:    $('card-'         + a.id),
        status:  $('card-status-'  + a.id),
        accuracy:$('accuracy-val-' + a.id),
        bar:     $('accuracy-bar-' + a.id),
        metrics: $('card-metrics-' + a.id),
        msg:     $('card-msg-'     + a.id),
        err:     $('card-err-'     + a.id),
        spinner: $('card-spin-'    + a.id),
      };
    });

    // Chips
    CHIPS.forEach(text => {
      const chip = document.createElement('button');
      chip.className = 'chip';
      chip.textContent = text;
      chip.addEventListener('click', () => {
        questionInput.value = text;
        questionInput.focus();
      });
      chipsContainer.appendChild(chip);
    });

    // Run button + enter key
    runBtn.addEventListener('click', startPipeline);
    questionInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startPipeline(); }
    });

    resetCards();
  }

  // ── Reset all cards to pending ─────────────────────────────────────────────

  function resetCards() {
    AGENTS.forEach(a => {
      const c = agentCards[a.id];
      setCardState(a.id, 'pending');
      c.accuracy.textContent = '—';
      c.bar.style.width      = '0%';
      c.metrics.innerHTML    = '<div class="idle-rows"></div>';
      c.msg.textContent      = '';
      c.err.textContent      = '';
    });

    flowNodes && Object.values(flowNodes).forEach(n => {
      if (n) n.className = 'flow-dot';
    });
    flowArrows && flowArrows.forEach(a => {
      if (a) a.classList.remove('lit');
    });

    if (summaryBar)  summaryBar.classList.remove('visible');
    if (resultPanel) resultPanel.classList.remove('visible');
  }

  // ── Set card visual state ──────────────────────────────────────────────────

  function setCardState(agentId, state) {
    const { card, status } = agentCards[agentId];
    card.className   = 'agent-card ' + state;
    const labels = { pending:'WAITING', active:'RUNNING', done:'DONE', error:'ERROR' };
    status.textContent = labels[state] || state.toUpperCase();
  }

  // ── Apply agent result to card ─────────────────────────────────────────────

  function applyResult(agentId, result, accuracy) {
    const agent = AGENTS.find(a => a.id === agentId);
    const c     = agentCards[agentId];

    // Accuracy number + bar
    const acc = accuracy ?? result?.accuracy ?? 0;
    c.accuracy.textContent = acc + '%';
    setTimeout(() => { c.bar.style.width = acc + '%'; }, 50);

    // Summary rows
    if (agent.summaryFn && result) {
      const rows = agent.summaryFn(result);
      c.metrics.innerHTML = rows.map(([k,v]) =>
        `<div class="metric-row">
           <span class="metric-key">${esc(k)}</span>
           <span class="metric-val">${esc(String(v))}</span>
         </div>`
      ).join('');
    }
  }

  // ── Update flow indicator ──────────────────────────────────────────────────

  function litFlow(agentIndex, done) {
    const id  = AGENTS[agentIndex].id;
    const dot = flowNodes[id];
    if (dot) {
      dot.className = 'flow-dot ' + (done ? 'done' : 'active');
    }
    if (done && agentIndex < flowArrows.length) {
      const arr = flowArrows[agentIndex];
      if (arr) arr.classList.add('lit');
    }
  }

  // ── Main pipeline runner ───────────────────────────────────────────────────

  async function startPipeline() {
    const question = (questionInput.value || '').trim();
    if (!question) {
      questionInput.focus();
      questionInput.classList.add('shake');
      setTimeout(() => questionInput.classList.remove('shake'), 400);
      return;
    }

    // Disable UI
    runBtn.disabled = true;
    runBtn.classList.add('loading');
    resetCards();

    try {
      await streamPipeline(question);
    } catch (err) {
      console.error('Pipeline error:', err);
    } finally {
      runBtn.disabled = false;
      runBtn.classList.remove('loading');
    }
  }

  async function streamPipeline(question) {
    const resp = await fetch('/api/agents/query', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ question, top_k: 10 }),
    });

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }

    const reader  = resp.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';

    // Track which agent index we're on for the flow bar
    const agentIndex = {};
    AGENTS.forEach((a, i) => { agentIndex[a.id] = i; });

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop();   // keep the incomplete last chunk

      for (const block of lines) {
        const line = block.trim();
        if (!line.startsWith('data:')) continue;
        let evt;
        try {
          evt = JSON.parse(line.slice(5).trim());
        } catch {
          continue;
        }
        handleEvent(evt, agentIndex);
      }
    }
  }

  function handleEvent(evt, agentIndex) {
    const { agent, status, result, accuracy, error, message, meta } = evt;

    // ── Per-agent events ───────────────────────────────────────────────────
    if (agent && status) {
      const idx = agentIndex[agent];

      if (status === 'active') {
        setCardState(agent, 'active');
        if (idx !== undefined) litFlow(idx, false);
        const c = agentCards[agent];
        if (c) c.msg.textContent = message || 'Processing…';
      }

      if (status === 'done') {
        setCardState(agent, 'done');
        if (idx !== undefined) litFlow(idx, true);
        applyResult(agent, result, accuracy);
        const c = agentCards[agent];
        if (c) c.msg.textContent = '';
      }

      if (status === 'error') {
        setCardState(agent, 'error');
        const c = agentCards[agent];
        if (c) {
          c.err.textContent = error || 'Unknown error';
          c.accuracy.textContent = '0%';
        }
      }
    }

    // ── Final complete event ──────────────────────────────────────────────
    if (evt.status === 'complete') {
      showFinalResult(evt);
    }
  }

  function showFinalResult(evt) {
    const { answer, sql, rows, columns, row_count, total_ms, avg_accuracy, agents } = evt;

    // Summary bar
    if (summaryBar) {
      $('sum-total-ms').textContent    = total_ms ? total_ms.toLocaleString() + ' ms' : '—';
      $('sum-avg-acc').textContent     = (avg_accuracy ?? 0) + '%';
      $('sum-rows').textContent        = (row_count ?? 0) + ' rows';
      summaryBar.classList.add('visible');
    }

    // Answer
    if (answerEl) {
      answerEl.textContent = answer || 'No answer returned.';
    }

    // SQL
    if (sqlCodeEl && sql) {
      sqlCodeEl.innerHTML = highlightSQL(sql);
    }

    // Table
    if (tableWrapEl && columns && columns.length > 0) {
      const thead = '<thead><tr>' + columns.map(c => `<th>${esc(c)}</th>`).join('') + '</tr></thead>';
      const tbody = '<tbody>' + (rows || []).slice(0, 100).map(row =>
        '<tr>' + row.map(cell => `<td>${esc(cell)}</td>`).join('') + '</tr>'
      ).join('') + '</tbody>';
      tableWrapEl.innerHTML = `<table class="data-table">${thead}${tbody}</table>`;
    } else if (tableWrapEl) {
      tableWrapEl.innerHTML = '<p style="color:var(--muted);padding:12px;font-size:12px;">No tabular data returned.</p>';
    }

    if (rowCountEl) {
      rowCountEl.textContent = (row_count ?? 0) + ' row' + ((row_count === 1) ? '' : 's');
    }

    if (resultPanel) {
      resultPanel.classList.add('visible');
      resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  // ── Boot ──────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', buildPage);
})();
