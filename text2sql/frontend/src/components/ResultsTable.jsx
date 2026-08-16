import { useState } from 'react'

const PAGE = 50

export default function ResultsTable({ columns, rows }) {
  const [page, setPage] = useState(0)
  const pages    = Math.ceil(rows.length / PAGE)
  const pageRows = rows.slice(page * PAGE, (page + 1) * PAGE)

  return (
    <div style={{
      background: 'var(--surface)', border: '1px solid var(--border)',
      borderRadius: 8, overflow: 'hidden',
    }}>
      {/* Bar */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '7px 14px', borderBottom: '1px solid var(--border)',
        background: 'var(--surface2)',
      }}>
        <span style={{
          fontSize: 10, fontFamily: 'var(--font-mono)',
          color: 'var(--text-muted)', letterSpacing: '1.2px', textTransform: 'uppercase',
        }}>Results</span>
        <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          {rows.length} row{rows.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{
          width: '100%', borderCollapse: 'collapse',
          fontFamily: 'var(--font-mono)', fontSize: 12,
        }}>
          <thead>
            <tr style={{ background: 'rgba(22,22,40,0.7)' }}>
              {columns.map(c => (
                <th key={c} style={{
                  padding: '8px 14px', textAlign: 'left',
                  color: 'var(--text-muted)', fontWeight: 500,
                  borderBottom: '1px solid var(--border)',
                  whiteSpace: 'nowrap', fontSize: 11, letterSpacing: '0.3px',
                }}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, i) => (
              <tr
                key={i}
                style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)', transition: 'background 0.1s' }}
                onMouseEnter={e => e.currentTarget.style.background = 'rgba(0,255,157,0.04)'}
                onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.012)'}
              >
                {row.map((cell, j) => (
                  <td key={j} style={{
                    padding: '7px 14px',
                    color: cell === null ? 'var(--text-muted)' : 'var(--text-dim)',
                    borderBottom: '1px solid rgba(30,30,53,0.6)',
                    whiteSpace: 'nowrap', maxWidth: 220,
                    overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {cell === null
                      ? <span style={{ opacity: 0.38, fontStyle: 'italic' }}>null</span>
                      : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div style={{
          display: 'flex', justifyContent: 'flex-end', alignItems: 'center',
          gap: 14, padding: '7px 14px', borderTop: '1px solid var(--border)',
          fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)',
        }}>
          <button
            disabled={page === 0}
            onClick={() => setPage(p => p - 1)}
            style={{ background: 'none', border: 'none', cursor: page === 0 ? 'default' : 'pointer', color: page === 0 ? 'var(--border-hi)' : 'var(--text-muted)', fontSize: 15 }}
          >←</button>
          <span>{page + 1} / {pages}</span>
          <button
            disabled={page === pages - 1}
            onClick={() => setPage(p => p + 1)}
            style={{ background: 'none', border: 'none', cursor: page === pages - 1 ? 'default' : 'pointer', color: page === pages - 1 ? 'var(--border-hi)' : 'var(--text-muted)', fontSize: 15 }}
          >→</button>
        </div>
      )}
    </div>
  )
}
