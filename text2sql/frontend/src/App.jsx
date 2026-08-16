import { useState, useCallback, useEffect } from 'react'
import GraphCanvas from './components/GraphCanvas'
import Sidebar from './components/Sidebar'
import ChatWindow from './components/ChatWindow'
import QueryInput from './components/QueryInput'

let _id = 0
const uid = () => ++_id

export default function App() {
  const [messages,  setMessages]  = useState([])
  const [loading,   setLoading]   = useState(false)
  const [domains,   setDomains]   = useState([])
  const [kgStatus,  setKgStatus]  = useState('connecting')

  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(d => setKgStatus(d.status === 'ok' ? 'connected' : 'error'))
      .catch(() => setKgStatus('error'))

    fetch('/api/domains')
      .then(r => r.json())
      .then(d => setDomains(d.domains || []))
      .catch(() => {})
  }, [])

  const sendQuery = useCallback(async (question) => {
    if (!question.trim() || loading) return
    const userId = uid()
    const aiId   = uid()

    setMessages(prev => [
      ...prev,
      { id: userId, role: 'user', text: question },
      { id: aiId,   role: 'assistant', status: 'loading', question },
    ])
    setLoading(true)

    try {
      const res  = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, top_k: 10 }),
      })
      const data = await res.json()
      setMessages(prev => prev.map(m =>
        m.id === aiId ? { ...m, status: data.success ? 'done' : 'error', ...data } : m
      ))
    } catch (err) {
      setMessages(prev => prev.map(m =>
        m.id === aiId ? { ...m, status: 'error', error: err.message } : m
      ))
    } finally {
      setLoading(false)
    }
  }, [loading])

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', position: 'relative' }}>
      <GraphCanvas />
      <Sidebar
        domains={domains}
        messages={messages}
        kgStatus={kgStatus}
        onSelect={sendQuery}
      />
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        position: 'relative', zIndex: 1, minWidth: 0,
      }}>
        <ChatWindow messages={messages} onSuggest={sendQuery} />
        <QueryInput onSend={sendQuery} loading={loading} />
      </div>
    </div>
  )
}
