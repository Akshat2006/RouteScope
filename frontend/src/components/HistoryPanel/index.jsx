/**
 * RouteScope — History Panel
 * Experiment list, save dialog, and side-by-side comparison.
 */
import { useState, useEffect } from 'react'
import { Save, BarChart2, Trash2, GitCompare } from 'lucide-react'
import axios from 'axios'
import useStore from '../../store/useStore'

export default function HistoryPanel() {
  const { algoResults, survivabilityScore, source, destination, experiments, setExperiments, addExperiment } = useStore()
  const [saveName, setSaveName] = useState('')
  const [saveDesc, setSaveDesc] = useState('')
  const [saving, setSaving] = useState(false)
  const [compareA, setCompareA] = useState('')
  const [compareB, setCompareB] = useState('')
  const [comparison, setComparison] = useState(null)
  const [loadingCompare, setLoadingCompare] = useState(false)

  useEffect(() => {
    axios.get('/api/experiments').then((r) => setExperiments(r.data.experiments || []))
  }, [])

  const handleSave = async () => {
    if (!saveName.trim()) return
    if (!algoResults) return
    setSaving(true)
    try {
      const body = {
        name: saveName,
        description: saveDesc,
        source, destination,
        results: algoResults.results,
        survivability_score: survivabilityScore,
        failure_events: [],
      }
      const res = await axios.post('/api/experiments', body)
      addExperiment({ id: res.data.experiment_id, name: saveName, description: saveDesc, created_at: new Date().toISOString(), survivability_score: survivabilityScore })
      setSaveName('')
      setSaveDesc('')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id) => {
    await axios.delete(`/api/experiments/${id}`)
    setExperiments(experiments.filter((e) => e.id !== id))
  }

  const handleCompare = async () => {
    if (!compareA || !compareB) return
    setLoadingCompare(true)
    try {
      const res = await axios.post('/api/experiments/compare', {
        experiment_id_a: Number(compareA),
        experiment_id_b: Number(compareB),
      })
      setComparison(res.data)
    } finally {
      setLoadingCompare(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, height: '100%', overflow: 'auto' }}>
      {/* Save current */}
      {algoResults && (
        <div style={{ padding: 12, borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontWeight: 700, fontSize: '0.8125rem', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Save size={14} style={{ color: 'var(--accent-purple)' }} /> Save Experiment
          </div>
          <div className="form-group" style={{ marginBottom: 6 }}>
            <input placeholder="Experiment name…" value={saveName} onChange={(e) => setSaveName(e.target.value)} />
          </div>
          <div className="form-group" style={{ marginBottom: 8 }}>
            <input placeholder="Description (optional)" value={saveDesc} onChange={(e) => setSaveDesc(e.target.value)} />
          </div>
          <button className="btn btn-primary w-full btn-sm" onClick={handleSave} disabled={saving || !saveName.trim()}>
            <Save size={12} /> {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}

      {/* Experiment list */}
      <div style={{ padding: 12, borderBottom: '1px solid var(--border)', flex: 1 }}>
        <div style={{ fontWeight: 700, fontSize: '0.8125rem', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <BarChart2 size={14} style={{ color: 'var(--accent-cyan)' }} /> Saved Experiments ({experiments.length})
        </div>
        {experiments.length === 0 && (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8125rem', textAlign: 'center', padding: 16 }}>
            No experiments saved yet
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {experiments.map((exp) => (
            <div key={exp.id} style={{
              background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
              padding: 10, display: 'flex', flexDirection: 'column', gap: 4,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, fontSize: '0.8125rem' }}>{exp.name}</span>
                <div style={{ display: 'flex', gap: 4 }}>
                  <span className="badge badge-purple">{(exp.survivability_score * 100).toFixed(0)}%</span>
                  <button className="btn btn-danger btn-sm" style={{ padding: '2px 6px' }} onClick={() => handleDelete(exp.id)}>
                    <Trash2 size={10} />
                  </button>
                </div>
              </div>
              <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
                {new Date(exp.created_at).toLocaleString()} · {exp.source} → {exp.destination}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Compare */}
      {experiments.length >= 2 && (
        <div style={{ padding: 12 }}>
          <div style={{ fontWeight: 700, fontSize: '0.8125rem', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
            <GitCompare size={14} style={{ color: 'var(--accent-orange)' }} /> Compare
          </div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
            <select value={compareA} onChange={(e) => setCompareA(e.target.value)} style={{ flex: 1 }}>
              <option value="">Exp A</option>
              {experiments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
            <select value={compareB} onChange={(e) => setCompareB(e.target.value)} style={{ flex: 1 }}>
              <option value="">Exp B</option>
              {experiments.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
          </div>
          <button className="btn btn-secondary w-full btn-sm" onClick={handleCompare} disabled={!compareA || !compareB || loadingCompare}>
            <GitCompare size={12} /> Compare
          </button>

          {comparison && (
            <div style={{ marginTop: 10 }}>
              <table className="exp-table">
                <thead>
                  <tr>
                    <th>Algorithm</th>
                    <th>{comparison.experiment_a.name}</th>
                    <th>{comparison.experiment_b.name}</th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.comparison.map((row) => (
                    <tr key={row.algorithm}>
                      <td style={{ fontWeight: 600 }}>{row.algorithm}</td>
                      <td>{row.a ? `${row.a.cost?.toFixed(2)} (${row.a.hops}h)` : '—'}</td>
                      <td>{row.b ? `${row.b.cost?.toFixed(2)} (${row.b.hops}h)` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
