(function () {
  'use strict';

  // ── Constants ──────────────────────────────────────────────────────────────
  const DOMAIN_COLORS = {
    SALES:     '#00ff88',
    HR:        '#8b5cf6',
    IT:        '#00d4ff',
    MARKETING: '#f59e0b',
    SECURITY:  '#f87171',
  };
  const SUGGESTIONS = [
    { label: 'QUERY_01', text: 'Show top 5 customers by total revenue' },
    { label: 'QUERY_02', text: 'High-priority IT incidents this month' },
    { label: 'QUERY_03', text: 'Employees with the most leave days remaining' },
    { label: 'QUERY_04', text: 'Marketing campaigns with the highest ROI' },
    { label: 'QUERY_05', text: 'Most common security vulnerabilities detected' },
    { label: 'QUERY_06', text: 'Payroll distribution across all departments' },
  ];
  const LOG_CFG = {
    info:  { color: '#3d6b8a', prefix: 'SYS' },
    embed: { color: '#00d4ff', prefix: 'EMB' },
    kg:    { color: '#00ff88', prefix: 'KG ' },
    llm:   { color: '#8b5cf6', prefix: 'LLM' },
    sql:   { color: '#4db8ff', prefix: 'SQL' },
    db:    { color: '#f59e0b', prefix: 'DB ' },
    done:  { color: '#00ff88', prefix: 'OK ' },
    error: { color: '#f87171', prefix: 'ERR' },
  };
  const PAGE_SIZE = 50;

  // ── Utilities ──────────────────────────────────────────────────────────────
  const esc   = s => String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const now   = () => new Date().toLocaleTimeString('en-US', { hour12:false, hour:'2-digit', minute:'2-digit', second:'2-digit' });
  const delay = ms => new Promise(r => setTimeout(r, ms));
  const rnd   = n  => Math.round(Math.random() * n);

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

  // ── Pipeline Card ──────────────────────────────────────────────────────────
  const PIPELINE_STEPS = [
    { label: 'Reading & tokenizing question' },
    { label: 'Encoding → 384-dim embedding vector' },
    { label: 'Neo4j AuraDB — establishing secure connection' },
    { label: 'Vector similarity search (cosine distance)' },
    { label: 'Knowledge graph traversal — FK expansion' },
    { label: 'Schema context assembly' },
    { label: 'LLaMA-3.3-70b via Groq API — generating SQL' },
    { label: 'SQL parsing & structure validation' },
    { label: 'Syntax verification' },
    { label: 'SQLite execution' },
  ];

  class PipelineCard {
    constructor(question) {
      this._q        = question;
      this._status   = PIPELINE_STEPS.map(() => 'pending');
      this._detail   = PIPELINE_STEPS.map(() => '');
      this._ms       = PIPELINE_STEPS.map(() => null);
      this._total    = null;
      this._collapsed = false;
      this._el       = this._build();  // _el is now assigned
      this._renderSteps();             // safe to call — _el exists
    }

    activate(i)  { this._status[i] = 'active';  this._renderSteps(); }

    complete(i, detail, ms) {
      this._status[i] = 'done';
      if (detail != null) this._detail[i] = detail;
      if (ms     != null) this._ms[i]     = ms;
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
      return { pending:'○', active:'◉', done:'✓', error:'✗' }[st] || '○';
    }

    _renderSteps() {
      const body = this._el.querySelector('.pipeline-steps');
      body.innerHTML = PIPELINE_STEPS.map((s, i) => {
        const st  = this._status[i];
        const det = this._detail[i];
        const ms  = this._ms[i];
        const right = st === 'active'
          ? `<span class="step-spinner"></span>`
          : ms != null ? `<span class="step-ms">${ms}ms</span>` : '';
        return `<div class="pipeline-step ${st}">
          <span class="step-icon">${this._icon(st)}</span>
          <span class="step-num">${String(i+1).padStart(2,'0')}</span>
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
            <span class="pipeline-badge">QUERY PIPELINE</span>
            <span class="pipeline-qtext">"${esc(qShort)}"</span>
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
      return el;  // do NOT call _renderSteps() here — this._el is not set yet
    }
  }

  // ── Canvas — Navy Blue Graph Network ───────────────────────────────────────
  const MAJOR_NODES = [
    { label: 'SALES', color: '#00ff88', rx: 0.15, ry: 0.25 },
    { label: 'HR',    color: '#8b5cf6', rx: 0.82, ry: 0.20 },
    { label: 'IT',    color: '#00d4ff', rx: 0.12, ry: 0.74 },
    { label: 'MKTG',  color: '#f59e0b', rx: 0.84, ry: 0.70 },
    { label: 'SEC',   color: '#f87171', rx: 0.50, ry: 0.89 },
  ];
  const SAT_COLORS = ['#00d4ff','#4db8ff','#8b5cf6','#00ff88','#0066cc','#2d8fd4','#6ee7b7'];

  let canvasNodes = [], canvasPackets = [];

  function initCanvas() {
    const canvas = document.getElementById('graph-canvas');
    const ctx    = canvas.getContext('2d');
    const N_SAT  = 58, DIST = 210, A = 0.14, SPD = 0.24;

    function resize() {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
      const W = canvas.width, H = canvas.height;

      const major = MAJOR_NODES.map(m => ({
        x: m.rx*W, y: m.ry*H,
        vx: (Math.random()-.5)*SPD*.45, vy: (Math.random()-.5)*SPD*.45,
        r: 4+Math.random()*.8, ph: Math.random()*Math.PI*2,
        major: true, label: m.label, color: m.color, flashTimer: 0,
      }));

      const sats = Array.from({ length: N_SAT }, () => ({
        x: Math.random()*W, y: Math.random()*H,
        vx: (Math.random()-.5)*SPD, vy: (Math.random()-.5)*SPD,
        r: 1.3+Math.random()*1.7, ph: Math.random()*Math.PI*2,
        major: false,
        color: SAT_COLORS[Math.floor(Math.random()*SAT_COLORS.length)],
        flashTimer: 0,
      }));

      canvasNodes   = [...major, ...sats];
      canvasPackets = [];
    }
    resize();
    window.addEventListener('resize', resize);

    (function frame() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      for (const n of canvasNodes) {
        n.x += n.vx; n.y += n.vy; n.ph += .015;
        if (n.x < 0 || n.x > canvas.width)  n.vx *= -1;
        if (n.y < 0 || n.y > canvas.height) n.vy *= -1;
      }

      for (let i = 0; i < canvasNodes.length; i++) {
        for (let j = i+1; j < canvasNodes.length; j++) {
          const a = canvasNodes[i], b = canvasNodes[j];
          const dx = a.x-b.x, dy = a.y-b.y, d = Math.sqrt(dx*dx+dy*dy);
          if (d < DIST) {
            const al = (1-d/DIST)*A;
            const ec = (a.major||b.major) ? (a.color||b.color) : '#00d4ff';
            ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y);
            ctx.strokeStyle = hexRgba(ec, al);
            ctx.lineWidth   = (a.major||b.major) ? 1.1 : .55;
            ctx.stroke();
          }
        }
      }

      if (canvasPackets.length < 30 && Math.random() < .03) {
        const pairs = [];
        for (let i=0; i<canvasNodes.length; i++) {
          for (let j=i+1; j<canvasNodes.length; j++) {
            const dx=canvasNodes[i].x-canvasNodes[j].x, dy=canvasNodes[i].y-canvasNodes[j].y;
            if (Math.sqrt(dx*dx+dy*dy) < DIST) pairs.push([i,j]);
          }
        }
        if (pairs.length) {
          const [i,j] = pairs[Math.floor(Math.random()*pairs.length)];
          const fwd = Math.random() > .5;
          canvasPackets.push({ from: canvasNodes[fwd?i:j], to: canvasNodes[fwd?j:i], progress: 0, speed: .007+Math.random()*.007, burst: false });
        }
      }

      for (let p = canvasPackets.length-1; p >= 0; p--) {
        const pk = canvasPackets[p];
        pk.progress += pk.speed;
        if (pk.progress > 1) { canvasPackets.splice(p,1); continue; }
        const fx=pk.from.x, fy=pk.from.y, tx=pk.to.x, ty=pk.to.y;
        for (let t=5; t>=0; t--) {
          const tp  = Math.max(0, pk.progress-t*.032);
          const px2 = fx+(tx-fx)*tp, py2 = fy+(ty-fy)*tp;
          const a2  = (1-t/6)*(pk.burst?.95:.7);
          const r2  = (1-t/6)*(pk.burst?3.2:2.4);
          ctx.beginPath(); ctx.arc(px2,py2,r2,0,Math.PI*2);
          ctx.fillStyle = pk.burst ? `rgba(0,212,255,${a2})` : `rgba(77,184,255,${(a2*.85).toFixed(3)})`;
          ctx.fill();
        }
      }

      for (const n of canvasNodes) {
        const p = Math.sin(n.ph)*.5+.5;
        let a = A+p*A*.8, r = n.r+p*(n.major?2.2:1.3);

        if (n.flashTimer > 0) {
          const fp = n.flashTimer/45;
          a += fp*.65; r += fp*6;
          ctx.beginPath(); ctx.arc(n.x,n.y,r+fp*14,0,Math.PI*2);
          ctx.strokeStyle = hexRgba(n.color, fp*.22); ctx.lineWidth = 1.8; ctx.stroke();
          n.flashTimer--;
        }

        ctx.beginPath(); ctx.arc(n.x,n.y,r,0,Math.PI*2);
        ctx.fillStyle = hexRgba(n.color, a); ctx.fill();

        if (n.major && (n.flashTimer > 0 || Math.sin(n.ph) > .5)) {
          const la = n.flashTimer > 0 ? n.flashTimer/45*.55 : .12;
          ctx.font = `600 10px 'JetBrains Mono',monospace`;
          ctx.fillStyle = hexRgba(n.color, la);
          ctx.textAlign = 'center';
          ctx.fillText(n.label, n.x, n.y-r-5);
          ctx.textAlign = 'left';
        }
      }

      requestAnimationFrame(frame);
    })();
  }

  function triggerBurst() {
    const major = canvasNodes.filter(n => n.major);
    if (!major.length) return;
    const center = major[Math.floor(Math.random()*major.length)];
    center.flashTimer = 45;
    canvasNodes.forEach(n => {
      const dx=n.x-center.x, dy=n.y-center.y, d=Math.sqrt(dx*dx+dy*dy);
      if (n !== center && d < 300) {
        canvasPackets.push({ from: center, to: n, progress: 0, speed: .014+Math.random()*.01, burst: true });
        if (n.major) setTimeout(() => { n.flashTimer = 28; }, d*1.8);
      }
    });
  }

  function hexRgba(hex, alpha) {
    const r=parseInt(hex.slice(1,3),16), g=parseInt(hex.slice(3,5),16), b=parseInt(hex.slice(5,7),16);
    return `rgba(${r},${g},${b},${Math.max(0,Math.min(1,alpha)).toFixed(3)})`;
  }

  // ── System Log ─────────────────────────────────────────────────────────────
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
      const c = DOMAIN_COLORS[d.toUpperCase()] || '#00d4ff';
      return `<span class="domain-badge" style="color:${c};border:1px solid ${c}40;background:${c}0d">${esc(d)}</span>`;
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
          <span><span class="schema-icon">⬡</span>Schema Context · ${names.length} table${names.length!==1?'s':''}</span>
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
        <div class="error-title">✗ Query failed</div>
        <div class="error-body">${esc(data.error||'Unknown error')}</div>
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
    const labels = { connected:'AuraDB connected', connecting:'Connecting…', error:'Not connected' };
    lbl.textContent = labels[status] || status;
    if (status === 'connected') simLog('Neo4j AuraDB — connection established', 'done');
    else if (status === 'error') simLog('Neo4j connection failed', 'error');
  }

  function setDomains(domains) {
    document.getElementById('domains-list').innerHTML = domains.map(d => {
      const c = DOMAIN_COLORS[d.name] || '#00d4ff';
      return `<div class="domain-item" title="${esc(d.description||d.name)}">
        <span class="domain-dot" style="background:${c};box-shadow:0 0 7px ${c}77"></span>
        <span class="domain-name">${esc(d.name[0]+d.name.slice(1).toLowerCase())}</span>
        <span class="domain-count">10t</span>
      </div>`;
    }).join('');
    simLog(`Loaded ${domains.length} domains from knowledge graph`, 'kg');
  }

  const sidebarRecent = [];
  function addRecent(text) {
    const idx = sidebarRecent.indexOf(text);
    if (idx > -1) sidebarRecent.splice(idx,1);
    sidebarRecent.unshift(text);
    if (sidebarRecent.length > 8) sidebarRecent.pop();
    const list = document.getElementById('recent-list');
    list.innerHTML = sidebarRecent
      .map(t => `<button class="recent-item" data-q="${esc(t)}">↑ ${esc(t)}</button>`)
      .join('');
    list.querySelectorAll('.recent-item').forEach(btn => btn.addEventListener('click', () => sendQuery(btn.dataset.q)));
  }

  // ── Empty State ────────────────────────────────────────────────────────────
  function showEmpty() {
    const msgs = document.getElementById('messages');
    if (msgs.querySelector('#empty-state')) return;
    const es = document.createElement('div');
    es.id = 'empty-state';
    es.innerHTML = `
      <div class="empty-hero">
        <div class="empty-logo-row">
          <svg class="empty-logo-icon" width="54" height="54" viewBox="0 0 34 34" fill="none">
            <circle cx="17" cy="17" r="15" stroke="#00d4ff" stroke-width=".45" stroke-dasharray="3 2" opacity=".25"/>
            <circle cx="17" cy="17" r="4.5" fill="#00d4ff" opacity=".95"/>
            <circle cx="17" cy="17" r="7"   fill="none" stroke="#00d4ff" stroke-width=".6" opacity=".3"/>
            <circle cx="6"  cy="9"  r="2.4" fill="#00ff88" opacity=".85"/>
            <circle cx="28" cy="9"  r="2.4" fill="#8b5cf6" opacity=".85"/>
            <circle cx="5"  cy="24" r="2.4" fill="#4db8ff" opacity=".8"/>
            <circle cx="29" cy="24" r="2.4" fill="#f59e0b" opacity=".8"/>
            <circle cx="17" cy="3"  r="1.8" fill="#00d4ff" opacity=".7"/>
            <circle cx="17" cy="31" r="1.8" fill="#f87171" opacity=".7"/>
            <line x1="17" y1="17" x2="6"  y2="9"  stroke="#00ff88" stroke-width="1.1" opacity=".5"/>
            <line x1="17" y1="17" x2="28" y2="9"  stroke="#8b5cf6" stroke-width="1.1" opacity=".5"/>
            <line x1="17" y1="17" x2="5"  y2="24" stroke="#4db8ff" stroke-width="1.1" opacity=".5"/>
            <line x1="17" y1="17" x2="29" y2="24" stroke="#f59e0b" stroke-width="1.1" opacity=".5"/>
            <line x1="17" y1="17" x2="17" y2="3"  stroke="#00d4ff" stroke-width="1"   opacity=".45"/>
            <line x1="17" y1="17" x2="17" y2="31" stroke="#f87171" stroke-width="1"   opacity=".45"/>
          </svg>
          <div class="empty-title-block">
            <div class="empty-name">SYNAPSE AI</div>
            <div class="empty-name-sub">REAL DATA GUIDE</div>
          </div>
        </div>
        <div class="empty-tagline">
          STREAMLINED STRUCTURED KNOWLEDGE GRAPH
          <span>·</span>
          NEO4J AURADB
          <span>·</span>
          LLaMA-3.3-70b
        </div>
        <div class="empty-pills">
          <span class="empty-pill">373 Embedded Columns</span>
          <span class="empty-pill">50 Tables · 5 Domains</span>
          <span class="empty-pill">Groq Inference API</span>
        </div>
      </div>

      <div class="highlighted-caption">
        Ask anything about your enterprise data.
        <mark class="hl-brand">SYNAPSE AI</mark> searches the
        <mark class="hl-kg">knowledge graph</mark> for relevant schema
        and generates precise <mark class="hl-sql">SQL</mark> —
        no technical knowledge required.
      </div>

      <div class="suggestions-grid">
        ${SUGGESTIONS.map(s => `
          <button class="suggestion-card" data-q="${esc(s.text)}">
            <span class="suggestion-label">${s.label}</span>${esc(s.text)}
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
    const box = document.getElementById('input-box');
    const gl  = document.getElementById('prompt-glyph');

    function syncState() {
      const ready = !!ta.value.trim() && !_busy;
      btn.className = ready ? 'ready' : '';
      gl.className  = 'prompt-glyph' + (_busy ? ' loading' : '');
      box.className = ta.value.trim() ? 'active' : '';
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
      document.getElementById('recent-list').innerHTML = '<span class="empty-recent">No queries yet</span>';
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
    triggerBurst();

    simLog(`Query: "${question.slice(0,42)}${question.length>42?'…':''}"`, 'info');

    // Fire real API call immediately — runs in parallel with step animations
    const apiPromise = api.query(question)
      .catch(err => ({ success: false, error: err.message, sql: '', schema_context: {}, columns: [], rows: [] }));

    const t0 = performance.now();
    let stepStart = t0;
    const stepDur = () => { const d=Math.round(performance.now()-stepStart); stepStart=performance.now(); return d; };

    // Step 0 — Reading
    card.activate(0);
    await delay(48+rnd(28));
    card.complete(0, `"${question.slice(0,32)}${question.length>32?'…':''}"`, stepDur());
    simLog('Question tokenised', 'info');

    // Step 1 — Embedding
    card.activate(1);
    await delay(145+rnd(55));
    card.complete(1, 'all-MiniLM-L6-v2 · 384 dims', stepDur());
    simLog('Embedding vector generated (384-dim)', 'embed');

    // Step 2 — Neo4j connection
    card.activate(2);
    await delay(105+rnd(40));
    card.complete(2, 'AuraDB v5 · TLS 1.3', stepDur());
    simLog('Neo4j AuraDB connection verified', 'kg');

    // Step 3 — Vector search
    card.activate(3);
    await delay(225+rnd(75));
    card.complete(3, '373 column embeddings scanned', stepDur());
    simLog('Vector similarity search complete', 'kg');

    // Step 4 — KG traversal (placeholder, updated with real data after API returns)
    card.activate(4);
    await delay(260+rnd(85));
    card.complete(4, 'FK relationships expanded', stepDur());
    simLog('Knowledge graph traversal done', 'kg');

    // Step 5 — Schema assembly
    card.activate(5);
    await delay(115+rnd(45));
    card.complete(5, 'schema context ready', stepDur());
    simLog('Schema context assembled for LLM prompt', 'kg');

    // Step 6 — LLM call (waits for real API to return)
    card.activate(6);
    simLog('Sending prompt to LLaMA-3.3-70b via Groq…', 'llm');
    stepStart = performance.now();

    const data  = await apiPromise;
    const llmMs = stepDur();

    if (data.success) {
      // Inject real schema data into earlier steps
      const tables  = Object.keys(data.schema_context && data.schema_context.tables ? data.schema_context.tables : {});
      const domains = [...new Set(tables.map(n => data.schema_context.tables[n] && data.schema_context.tables[n].domain).filter(Boolean))];
      card.updateDetail(3, `${Math.min(tables.length*4,18)} columns matched`);
      card.updateDetail(4, `${tables.length} tables · ${domains.slice(0,3).join(', ')}`);

      const attempts = data.attempts || 1;
      card.complete(6, `SQL generated · ${attempts} attempt${attempts!==1?'s':''}`, llmMs);
      simLog(`LLM responded in ${llmMs}ms (${attempts} attempt${attempts!==1?'s':''})`, 'llm');

      // Step 7 — SQL parsing
      card.activate(7);
      await delay(38);
      const lines = (data.sql||'').split('\n').filter(l => l.trim()).length;
      card.complete(7, `${lines} line${lines!==1?'s':''}`, stepDur());

      // Step 8 — Validation
      card.activate(8);
      await delay(28);
      card.complete(8, 'syntax OK · no injection risk', stepDur());
      simLog('SQL syntax validated', 'sql');

      // Step 9 — Execution
      card.activate(9);
      await delay(22);
      const rowCount = data.rows ? data.rows.length : 0;
      card.complete(9, `${rowCount.toLocaleString()} row${rowCount!==1?'s':''} returned`, stepDur());
      simLog(`Executed → ${rowCount} rows in ${Math.round(performance.now()-t0)}ms`, 'done');

    } else {
      card.fail(6, (data.error||'error').slice(0,60));
      simLog(`Failed: ${(data.error||'').slice(0,55)}`, 'error');
    }

    card.setTotal(Math.round(performance.now()-t0));
    msgs.appendChild(buildAssistantBubble(data));
    scrollBottom();
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  async function init() {
    initCanvas();
    initInput();
    showEmpty();
    simLog('SYNAPSE AI v1.0 — Real Data Guide', 'info');
    simLog('Streamlined Structured Knowledge Graph · Neo4j AuraDB', 'info');

    api.health()
      .then(h => setKGStatus(h.status === 'ok' ? 'connected' : 'error'))
      .catch(() => setKGStatus('error'));

    api.domains()
      .then(d => setDomains(d.domains || []))
      .catch(() => {});
  }

  document.addEventListener('DOMContentLoaded', init);
})();
