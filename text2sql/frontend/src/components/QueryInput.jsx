import { useState, useRef } from 'react'

export default function QueryInput({ onSend, loading }) {
  const [value, setValue] = useState('')
  const ref = useRef(null)

  const submit = () => {
    const q = value.trim()
    if (!q || loading) return
    onSend(q)
    setValue('')
    if (ref.current) ref.current.style.height = 'auto'
  }

  const onKey = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
  }

  const onInput = e => {
    setValue(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
  }

  const canSend = !!value.trim() && !loading

  return (
    <div style={{
      padding: '12px 28px 20px',
      borderTop: '1px solid var(--border)',
      background: 'rgba(5,5,8,0.96)',
      backdropFilter: 'blur(14px)',
      zIndex: 2,
    }}>
      <div style={{
        maxWidth: 820, margin: '0 auto',
        display: 'flex', alignItems: 'flex-end', gap: 10,
        background: 'var(--surface)',
        border: `1px solid ${canSend ? 'rgba(0,255,157,0.25)' : 'var(--border)'}`,
        borderRadius: 12, padding: '10px 10px 10px 16px',
        transition: 'border-color 0.2s',
        boxShadow: canSend ? '0 0 0 1px rgba(0,255,157,0.08)' : 'none',
      }}>

        {/* Prompt glyph */}
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 14, flexShrink: 0, paddingBottom: 2,
          color: loading ? 'var(--text-muted)' : 'var(--accent)',
          animation: loading ? 'pulse 1.4s ease-in-out infinite' : 'none',
          transition: 'color 0.2s',
        }}>
          {loading ? '◈' : '>_'}
        </span>

        <textarea
          ref={ref}
          value={value}
          onChange={onInput}
          onKeyDown={onKey}
          disabled={loading}
          placeholder="Ask anything about your enterprise data…"
          rows={1}
          style={{
            flex: 1, background: 'none', border: 'none', outline: 'none',
            color: loading ? 'var(--text-muted)' : 'var(--text)',
            fontFamily: 'var(--font-sans)', fontSize: 14, lineHeight: 1.65,
            resize: 'none', overflowY: 'hidden',
          }}
        />

        <button
          onClick={submit}
          disabled={!canSend}
          style={{
            width: 36, height: 36, borderRadius: 8, border: 'none',
            background: canSend ? 'var(--accent)' : 'var(--surface2)',
            color: canSend ? '#050508' : 'var(--text-muted)',
            cursor: canSend ? 'pointer' : 'default',
            flexShrink: 0, fontSize: 17,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            transition: 'all 0.2s',
            boxShadow: canSend ? '0 0 12px rgba(0,255,157,0.3)' : 'none',
          }}
        >
          {loading
            ? <span style={{ animation: 'pulse 0.9s ease-in-out infinite', fontSize: 9 }}>●</span>
            : '↑'}
        </button>
      </div>

      <div style={{
        maxWidth: 820, margin: '6px auto 0',
        textAlign: 'center', fontSize: 10,
        fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', opacity: 0.45,
      }}>
        Enter ↵ to send · Shift+Enter for new line
      </div>
    </div>
  )
}
