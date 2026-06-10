/**
 * RouteScope — WebSocket Hook
 *
 * Connects to /ws, parses incoming messages, and dispatches them
 * to the Zustand store. Handles reconnection automatically.
 */
import { useEffect, useRef, useCallback } from 'react'
import useStore from '../store/useStore'

const WS_URL = `ws://${window.location.host}/ws`
const RECONNECT_DELAY = 3000

export function useWebSocket() {
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)
  const {
    setWsStatus,
    setGraph,
    updateMetrics,
    setAlgoResults,
    addFailure,
    clearFailures,
    setComputing,
  } = useStore()

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setWsStatus('connecting')
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws

    ws.onopen = () => {
      setWsStatus('connected')
      clearTimeout(reconnectTimer.current)
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)

        switch (msg.type) {
          case 'graph_update':
            setGraph(msg.data, msg.health, msg.live, msg.storage_tier, msg.storage_backend)
            break

          case 'metric_update':
            updateMetrics(msg.data)
            break

          case 'algo_results':
            setAlgoResults(msg.data)
            setComputing(false)
            break

          case 'failure_event':
            if (msg.data?.graph) {
              setGraph(msg.data.graph, msg.data.health)
            }
            if (msg.data?.affected) {
              addFailure({
                type: msg.data.event_type,
                affected: msg.data.affected,
                timestamp: new Date().toISOString(),
              })
            }
            break

          case 'pong':
            break

          default:
            break
        }
      } catch (e) {
        console.warn('WS parse error:', e)
      }
    }

    ws.onclose = () => {
      setWsStatus('disconnected')
      reconnectTimer.current = setTimeout(() => connect(), RECONNECT_DELAY)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [setWsStatus, setGraph, updateMetrics, setAlgoResults, addFailure, clearFailures, setComputing])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback((msg) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  const computeViaWS = useCallback((source, destination) => {
    setComputing(true)
    send({ type: 'compute', source, destination })
  }, [send, setComputing])

  const ping = useCallback(() => send({ type: 'ping' }), [send])

  return { send, computeViaWS, ping }
}
