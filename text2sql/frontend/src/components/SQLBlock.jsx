import { useState } from 'react'

const KW = new Set([
  'SELECT','FROM','WHERE','JOIN','INNER','LEFT','RIGHT','OUTER','FULL','CROSS',
  'ON','GROUP','BY','ORDER','HAVING','LIMIT','OFFSET','AS','AND','OR','NOT',
  'IN','LIKE','BETWEEN','IS','NULL','DISTINCT','WITH','UNION','ALL','INTERSECT',
  'EXCEPT','CASE','WHEN','THEN','ELSE','END','INSERT','INTO','VALUES','UPDATE',
  'SET','DELETE','CREATE','DROP','ALTER','TABLE','ASC','DESC','EXISTS','OVER',
  'PARTITION','ROWS','RANGE','RECURSIVE',
])
const FN = new Set([
  'COUNT','SUM','AVG','MAX','MIN','COALESCE','CAST','ROUND','ABS','UPPER',
  'LOWER','TRIM','LENGTH','SUBSTR','SUBSTRING','REPLACE','IFNULL','NULLIF',
  'IIF','STRFTIME','DATE','DATETIME','JULIANDAY','TYPEOF','RANDOM','HEX',
  'ROW_NUMBER','RANK','DENSE_RANK','LAG','LEAD','FIRST_VALUE','LAST_VALUE',
])

function tokenize(sql) {
  const out = []
  let i = 0
  while (i < sql.length) {
    // Whitespace
    if (/\s/.test(sql[i])) {
      let j = i; while (j < sql.length && /\s/.test(sql[j])) j++
      out.push({ t: 'ws', v: sql.slice(i, j) }); i = j; continue
    }
    // Line comment
    if (sql[i] === '-' && sql[i+1] === '-') {
      let j = i; while (j < sql.length && sql[j] !== '\n') j++
      out.push({ t: 'comment', v: sql.slice(i, j) }); i = j; continue
    }
    // String
    if (sql[i] === "'") {
      let j = i + 1; while (j < sql.length && sql[j] !== "'") j++
      out.push({ t: 'str', v: sql.slice(i, j + 1) }); i = j + 1; continue
    }
    // Number
    if (/\d/.test(sql[i])) {
      let j = i; while (j < sql.length && /[\d.]/.test(sql[j])) j++
      out.push({ t: 'num', v: sql.slice(i, j) }); i = j; continue
    }
    // Word (keyword / function / ident)
    if (/[a-zA-Z_]/.test(sql[i])) {
      let j = i; while (j < sql.length && /[\w]/.test(sql[j])) j++
      const w = sql.slice(i, j), u = w.toUpperCase()
      out.push({ t: KW.has(u) ? 'kw' : FN.has(u) ? 'fn' : 'id', v: w }); i = j; continue
    }
    // Operator
    if (/[=<>!*]/.test(sql[i])) {
      let j = i; while (j < sql.length && /[=<>!*]/.test(sql[j])) j++
      out.push({ t: 'op', v: sql.slice(i, j) }); i = j; continue
    }
    out.push({ t: 'pt', v: sql[i] }); i++
  }
  return out
}

const COLORS = {
  kw:      'var(--sql-kw)',
  fn:      'var(--sql-fn)',
  str:     'var(--sql-str)',
  num:     'var(--sql-num)',
  comment: 'var(--sql-comment)',
  op:      'var(--sql-op)',
  id:      'var(--text)',
  pt:      'var(--sql-punct)',
  ws:      null,
}

export default function SQLBlock({ sql }) {
  const [copied, setCopied] = useState(false)
  const tokens = tokenize(sql)

  const copy = () => {
    navigator.clipboard.writeText(sql).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 8, overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '7px 14px', borderBottom: '1px solid var(--border)',
        background: 'var(--surface2)',
      }}>
        <span style={{
          fontSize: 10, fontFamily: 'var(--font-mono)',
          color: 'var(--text-muted)', letterSpacing: '1.2px', textTransform: 'uppercase',
        }}>SQL</span>
        <button onClick={copy} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 11, fontFamily: 'var(--font-mono)',
          color: copied ? 'var(--accent)' : 'var(--text-muted)',
          padding: '2px 8px', borderRadius: 4, transition: 'color 0.2s',
        }}>
          {copied ? '✓ copied' : '⎘ copy'}
        </button>
      </div>
      <pre style={{
        padding: '14px 16px', margin: 0,
        fontFamily: 'var(--font-mono)', fontSize: 13,
        lineHeight: 1.75, overflowX: 'auto', whiteSpace: 'pre',
      }}>
        {tokens.map((tok, i) => {
          const c = COLORS[tok.t]
          return c
            ? <span key={i} style={{ color: c }}>{tok.v}</span>
            : tok.v
        })}
      </pre>
    </div>
  )
}
