const DOMAIN_COLOR = {
  SALES:     '#00ff9d',
  HR:        '#a78bfa',
  IT:        '#22d3ee',
  MARKETING: '#fbbf24',
  SECURITY:  '#f87171',
}

export default function Sidebar({ domains, messages, kgStatus, onSelect }) {
  const recent = messages
    .filter(m => m.role === 'user')
    .slice(-7)
    .reverse()

  const dot = {
    connected:  'var(--accent)',
    connecting: 'var(--amber)',
    error:      'var(--red)',
  }[kgStatus] ?? 'var(--text-muted)'

  return (
    <aside style={{
      width: 256,
      flexShrink: 0,
      borderRight: '1px solid var(--border)',
      background: 'rgba(10, 10, 18, 0.88)',
      backdropFilter: 'blur(16px)',
      display: 'flex',
      flexDirection: 'column',
      zIndex: 2,
    }}>

      {/* Logo */}
      <div style={{ padding: '22px 18px 16px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--accent)', letterSpacing: '-0.3px' }}>
            DataPulse
          </span>
          <span style={{ color: 'var(--text-muted)', margin: '0 6px', fontSize: 13 }}>∴</span>
          <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>KG</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
            background: dot,
            animation: kgStatus === 'connected' ? 'pulse 2.2s ease-in-out infinite' : 'none',
          }} />
          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
            {kgStatus === 'connected' ? 'Neo4j connected' : kgStatus === 'connecting' ? 'Connecting…' : 'Not connected'}
          </span>
        </div>
      </div>

      {/* Domains */}
      <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', letterSpacing: '1.4px', textTransform: 'uppercase', marginBottom: 10 }}>
          Domains
        </div>
        {domains.map(d => (
          <div key={d.name} style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 7 }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
              background: DOMAIN_COLOR[d.name] || 'var(--accent)',
              boxShadow: `0 0 5px ${DOMAIN_COLOR[d.name] || 'var(--accent)'}55`,
            }} />
            <span style={{ fontSize: 12, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
              {d.name.charAt(0) + d.name.slice(1).toLowerCase()}
            </span>
          </div>
        ))}
      </div>

      {/* Recent queries */}
      <div style={{ padding: '14px 18px', flex: 1, overflowY: 'auto' }}>
        <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', letterSpacing: '1.4px', textTransform: 'uppercase', marginBottom: 10 }}>
          Recent
        </div>
        {recent.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>No queries yet</div>
        ) : recent.map(m => (
          <button key={m.id} onClick={() => onSelect(m.text)} style={{
            display: 'block', width: '100%', background: 'none', border: 'none',
            cursor: 'pointer', textAlign: 'left', padding: '6px 8px', borderRadius: 6,
            color: 'var(--text-muted)', fontSize: 12, fontFamily: 'var(--font-sans)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            transition: 'all 0.15s', marginBottom: 2,
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface2)'; e.currentTarget.style.color = 'var(--text)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            ↑ {m.text}
          </button>
        ))}
      </div>

      {/* Stats footer */}
      <div style={{
        padding: '10px 18px',
        borderTop: '1px solid var(--border)',
        display: 'flex',
        justifyContent: 'space-between',
        fontSize: 10,
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-muted)',
      }}>
        <span>50 tables</span>
        <span>373 cols</span>
        <span>23k rows</span>
      </div>
    </aside>
  )
}
