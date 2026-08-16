import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'

const SUGGESTIONS = [
  { label: 'QUERY_01', text: 'Top 5 customers by total revenue' },
  { label: 'QUERY_02', text: 'High-priority IT incidents this month' },
  { label: 'QUERY_03', text: 'Employees with the most leave days remaining' },
  { label: 'QUERY_04', text: 'Marketing campaigns with highest ROI' },
  { label: 'QUERY_05', text: 'Most common security vulnerabilities detected' },
  { label: 'QUERY_06', text: 'Payroll distribution across departments' },
]

export default function ChatWindow({ messages, onSuggest }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (messages.length === 0) return <EmptyState onSuggest={onSuggest} />

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '0 28px' }}>
      <div style={{ maxWidth: 820, margin: '0 auto', paddingTop: 28, paddingBottom: 16 }}>
        {messages.map((msg, i) => (
          <MessageBubble key={msg.id} message={msg} delay={i * 0.04} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

function EmptyState({ onSuggest }) {
  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center',
      padding: '40px 28px', gap: 36,
      animation: 'fadeIn 0.5s ease-out',
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 30, fontWeight: 600,
          color: 'var(--accent)', letterSpacing: '-1px', marginBottom: 10,
          textShadow: '0 0 30px rgba(0,255,157,0.4)',
        }}>
          DataPulse ∴ KG
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', maxWidth: 360, lineHeight: 1.7 }}>
          Ask anything about your enterprise data in plain English.
          The knowledge graph finds the right tables — the LLM writes the SQL.
        </div>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)',
        gap: 10, maxWidth: 620, width: '100%',
      }}>
        {SUGGESTIONS.map((s, i) => (
          <button
            key={i}
            onClick={() => onSuggest(s.text)}
            style={{
              background: 'rgba(12, 12, 20, 0.75)',
              border: '1px solid var(--border)',
              borderRadius: 10, padding: '14px 16px',
              color: 'var(--text-dim)', fontSize: 13,
              fontFamily: 'var(--font-sans)', textAlign: 'left',
              cursor: 'pointer', transition: 'all 0.2s',
              backdropFilter: 'blur(10px)', lineHeight: 1.5,
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'rgba(0,255,157,0.28)'
              e.currentTarget.style.color       = 'var(--text)'
              e.currentTarget.style.background  = 'rgba(0,255,157,0.04)'
              e.currentTarget.style.transform   = 'translateY(-1px)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.color       = 'var(--text-dim)'
              e.currentTarget.style.background  = 'rgba(12,12,20,0.75)'
              e.currentTarget.style.transform   = 'none'
            }}
          >
            <span style={{
              display: 'block', fontSize: 9, color: 'var(--accent)',
              fontFamily: 'var(--font-mono)', marginBottom: 5, letterSpacing: '1.2px',
            }}>
              {s.label}
            </span>
            {s.text}
          </button>
        ))}
      </div>
    </div>
  )
}
