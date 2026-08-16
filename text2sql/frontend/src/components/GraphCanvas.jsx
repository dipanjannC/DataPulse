import { useEffect, useRef } from 'react'

const N      = 48
const SPEED  = 0.28
const DIST   = 175
const ALPHA  = 0.11

function mkNode(w, h) {
  return {
    x:  Math.random() * w,
    y:  Math.random() * h,
    vx: (Math.random() - 0.5) * SPEED,
    vy: (Math.random() - 0.5) * SPEED,
    r:  Math.random() * 1.8 + 1.2,
    ph: Math.random() * Math.PI * 2,
  }
}

export default function GraphCanvas() {
  const ref   = useRef(null)
  const state = useRef({ nodes: [], raf: null })

  useEffect(() => {
    const canvas = ref.current
    const ctx    = canvas.getContext('2d')

    const resize = () => {
      canvas.width  = window.innerWidth
      canvas.height = window.innerHeight
      state.current.nodes = Array.from({ length: N }, () =>
        mkNode(canvas.width, canvas.height)
      )
    }
    resize()
    window.addEventListener('resize', resize)

    function frame() {
      const { nodes }     = state.current
      const { width: w, height: h } = canvas
      ctx.clearRect(0, 0, w, h)

      for (const n of nodes) {
        n.x  += n.vx
        n.y  += n.vy
        n.ph += 0.018
        if (n.x < 0 || n.x > w) n.vx *= -1
        if (n.y < 0 || n.y > h) n.vy *= -1
      }

      // Edges
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x
          const dy = nodes[i].y - nodes[j].y
          const d  = Math.sqrt(dx * dx + dy * dy)
          if (d < DIST) {
            const a = (1 - d / DIST) * ALPHA
            ctx.beginPath()
            ctx.moveTo(nodes[i].x, nodes[i].y)
            ctx.lineTo(nodes[j].x, nodes[j].y)
            ctx.strokeStyle = `rgba(0,255,157,${a})`
            ctx.lineWidth   = 0.6
            ctx.stroke()
          }
        }
      }

      // Nodes
      for (const n of nodes) {
        const p = Math.sin(n.ph) * 0.5 + 0.5
        const a = ALPHA + p * ALPHA * 0.6
        ctx.beginPath()
        ctx.arc(n.x, n.y, n.r + p * 1.4, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(0,255,157,${a})`
        ctx.fill()
      }

      state.current.raf = requestAnimationFrame(frame)
    }
    state.current.raf = requestAnimationFrame(frame)

    return () => {
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(state.current.raf)
    }
  }, [])

  return (
    <canvas
      ref={ref}
      style={{
        position: 'fixed', inset: 0,
        width: '100%', height: '100%',
        pointerEvents: 'none',
        zIndex: 0,
      }}
    />
  )
}
