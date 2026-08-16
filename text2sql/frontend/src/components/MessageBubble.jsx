import { useState, useEffect } from 'react'
import SQLBlock from './SQLBlock'
import ResultsTable from './ResultsTable'

const DOMAIN_COLOR = {
  SALES:     '#00ff9d',
  HR:        '#a78bfa',
  IT:        '#22d3ee',
  MARKETING: '#fbbf24',
  SECURITY:  '#f87171',
}

export default function MessageBubble({ message, delay = 0 }) {
  if (message.role === 'user') return <UserBubble text={message.text} delay={delay} />
  return <AssistantBubble message={message} delay={delay} />
}

function UserBubble({ text, delay }) {
  return (
    <div className="animate-in" style={{
      display: 'flex', justifyContent: 'flex-end',
      marginBottom: 20, animationDelay: `${delay}s`,
    }}>
      <div style={{
        maxWidth: '72%',
        background: 'rgba(124, 58, 237, 0.14)',
        border: '1px solid rgba(124, 58, 237, 0.28)',
        borderRadius: '12px 12px 3px 12px',
        padding: '11px 16px',
        color: 'var(--text)', fontSize: 14, lineHeight: 1.65,
      }}>
        {text}
      </div>
    </div>
  )
}

function AssistantBubble({ message, delay }) {
  const [schemaOpen, setSchemaOpen] = useState(false)

  if (message.status === 'loading') return <LoadingBubble />

  const tables  = message.schema_context?.tables || {}
  const domains = [...new Set(Object.values(tables).map(t => t.domain).filter(Boolean))]

  return (
    <div className="animate-in" style={{ marginBottom: 28, animationDelay: `${delay}s` }}>

      {/* Domain badges */}
      {domains.length > 0 && (
        <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          {domains.map(d => (
            <span key={d} style={{
              fontSize: 10, fontFamily: 'var(--font-mono)', letterSpacing: '0.8px',
              padding: '2px 9px', borderRadius: 4,
              border: `1px solid ${(DOMAIN_COLOR[d] || '#00ff9d')}40`,
              color: DOMAIN_COLOR[d] || '#00ff9d',
              background: `${DOMAIN_COLOR[d] || '#00ff9d'}0e`,
            }}>
              {d}
            </span>
          ))}
        </div>
      )}

      {message.status === 'error' ? (
        <ErrorCard error={message.error} sql={message.sql} />
      ) : (
        <>
          {/* Schema toggle */}
          {Object.keys(tables).length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <SchemaToggle
                tables={tables}
                open={schemaOpen}
                onToggle={() => setSchemaOpen(o => !o)}
              />
            </div>
          )}

          {/* SQL */}
          {message.sql && (
            <div className="animate-in" style={{ marginBottom: 10, animationDelay: '0.08s' }}>
              <SQLBlock sql={message.sql} />
            </div>
          )}

          {/* Results */}
          {message.columns?.length > 0 && (
            <div className="animate-in" style={{ animationDelay: '0.16s' }}>
              <ResultsTable columns={message.columns} rows={message.rows || []} />
            </div>
          )}
        </>
      )}
    </div>
  )
}

const LOAD_PHASES = ['Scanning knowledge graph', 'Generating SQL', 'Executing query']

function LoadingBubble() {
  const [phase, setPhase] = useState(0)
  const [dots,  setDots]  = useState('.')

  useEffect(() => {
    const iv = setInterval(() => setPhase(p => Math.min(p + 1, LOAD_PHASES.length - 1)), 1800)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    const iv = setInterval(() => setDots(d => d.length >= 3 ? '.' : d + '.'), 380)
    return () => clearInterval(iv)
  }, [])

  return (
    <div style={{ marginBottom: 24 }}>
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 10,
        padding: '11px 16px',
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 10, fontSize: 13, fontFamily: 'var(--font-mono)',
        color: 'var(--text-muted)',
      }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
          background: 'var(--accent)',
          animation: 'pulse 0.9s ease-in-out infinite',
        }} />
        {LOAD_PHASES[phase]}
        <span style={{ color: 'var(--accent)', minWidth: 18 }}>{dots}</span>
      </div>
    </div>
  )
}

function SchemaToggle({ tables, open, onToggle }) {
  const names = Object.keys(tables)
  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 8, overflow: 'hidden',
    }}>
      <button onClick={onToggle} style={{
        width: '100%', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', padding: '8px 14px',
        background: 'none', border: 'none', cursor: 'pointer',
        color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-mono)',
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ color: 'var(--accent)', fontSize: 11 }}>⬡</span>
          Schema retrieved · {names.length} table{names.length !== 1 ? 's' : ''}
        </span>
        <span style={{ transition: 'transform 0.2s', transform: open ? 'rotate(180deg)' : 'none', fontSize: 12 }}>▾</span>
      </button>
      {open && (
        <div style={{ padding: '0 14px 10px', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {names.map(n => (
            <span key={n} style={{
              fontSize: 11, fontFamily: 'var(--font-mono)',
              color: 'var(--text-dim)', background: 'var(--surface2)',
              border: '1px solid var(--border)', padding: '2px 8px', borderRadius: 4,
            }}>
              {n}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function ErrorCard({ error, sql }) {
  return (
    <div style={{
      background: 'rgba(248,113,113,0.06)',
      border: '1px solid rgba(248,113,113,0.22)',
      borderRadius: 8, padding: '12px 16px',
    }}>
      <div style={{ fontSize: 12, color: 'var(--red)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
        ✗ Query failed
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{error}</div>
      {sql && (
        <div style={{
          marginTop: 10, fontSize: 12, fontFamily: 'var(--font-mono)',
          color: 'var(--text-muted)', whiteSpace: 'pre-wrap', opacity: 0.55,
        }}>
          {sql}
        </div>
      )}
    </div>
  )
}
