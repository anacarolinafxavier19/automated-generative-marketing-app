import { useCallback, useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function StatTile({ label, value, sub }) {
  return (
    <div className="stat-tile">
      <p className="label">{label}</p>
      <p className="value">{value}</p>
      {sub && <p className="sub">{sub}</p>}
    </div>
  )
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="tooltip-box">
      <div>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey}>
          {p.name}: {typeof p.value === 'number' ? p.value.toLocaleString() : p.value}
        </div>
      ))}
    </div>
  )
}

function fmtPct(v) {
  return v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`
}

function fmtEur(v) {
  if (v === null || v === undefined) return '—'
  return `€${v < 0.01 ? v.toFixed(6) : v.toFixed(4)}`
}

function AlertsPanel({ alerts }) {
  if (!alerts || alerts.length === 0) {
    return <div className="empty-state">No alerts — run the app-evaluator agent to generate a report.</div>
  }
  const order = { critical: 0, warning: 1, info: 2 }
  const sorted = [...alerts].sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3))
  return (
    <div className="alert-list">
      {sorted.map((a, i) => (
        <div className="alert-row" key={i}>
          <span className={`alert-badge ${a.severity}`}>{a.severity}</span>
          <div className="alert-body">
            <p className="message">{a.message}</p>
            {a.file && <p className="file">{a.file}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}

function SuggestionsPanel({ suggestions }) {
  if (!suggestions || suggestions.length === 0) {
    return <div className="empty-state">No suggestions yet — run the app-evaluator agent.</div>
  }
  return (
    <div>
      {suggestions.map((s, i) => (
        <div className="suggestion-card" key={i}>
          <div className="title-row">
            <strong>{s.title}</strong>
            <span className="priority-pill">{s.priority}</span>
          </div>
          <p>{s.detail}</p>
        </div>
      ))}
    </div>
  )
}

export default function App() {
  const [metrics, setMetrics] = useState(null)
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  const load = useCallback(async () => {
    try {
      const metricsResp = await fetch(`${API_URL}/metrics`)
      if (!metricsResp.ok) throw new Error(`GET /metrics -> HTTP ${metricsResp.status}`)
      setMetrics(await metricsResp.json())
      setError(null)
    } catch (e) {
      setError(e.message)
    }

    try {
      const reportResp = await fetch(`${API_URL}/evaluation-report`)
      setReport(reportResp.ok ? await reportResp.json() : null)
    } catch {
      setReport(null)
    }

    setLastUpdated(new Date())
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [load])

  const summary = metrics?.summary
  const records = metrics?.records ?? []
  const chronological = [...records].reverse()

  const latencyData = chronological.map((r, i) => ({
    idx: i + 1,
    label: `${r.sender_company} → ${r.receiver_company}`,
    latency: Number(r.latency_seconds.toFixed(2)),
  }))

  const tokenData = chronological.map((r, i) => ({
    idx: i + 1,
    label: `${r.sender_company} → ${r.receiver_company}`,
    input: r.input_tokens,
    output: r.output_tokens,
  }))

  return (
    <>
      <div className="dashboard-header">
        <div>
          <h1>marketing-app evaluation dashboard</h1>
          <p>
            {API_URL} · {lastUpdated ? `updated ${lastUpdated.toLocaleTimeString()}` : 'loading…'}
            {error && <span style={{ color: 'var(--status-critical)' }}> · {error}</span>}
          </p>
        </div>
        <button className="refresh-btn" onClick={load}>Refresh</button>
      </div>

      <div className="section">
        <h2>Agentic AI metrics</h2>
        {!summary || summary.total_generations === 0 ? (
          <div className="empty-state">
            No generations recorded yet. Run <code>.claude/skills/run-marketing-app/smoke.sh</code> to produce data.
          </div>
        ) : (
          <>
            <div className="tile-grid">
              <StatTile label="Total generations" value={summary.total_generations} />
              <StatTile label="First-pass success" value={fmtPct(summary.first_pass_success_rate)} sub="no repair pass needed" />
              <StatTile label="Repair-pass rate" value={fmtPct(summary.repair_pass_rate)} />
              <StatTile label="Repair success rate" value={fmtPct(summary.repair_success_rate)} sub="of those repaired" />
              <StatTile label="Avg latency" value={`${summary.avg_latency_seconds}s`} sub={`p50 ${summary.p50_latency_seconds}s`} />
              <StatTile label="Avg chunks retrieved" value={`${summary.avg_sender_chunks_used} / ${summary.avg_receiver_chunks_used}`} sub="sender / receiver" />
              <StatTile label="Total tokens" value={(summary.total_input_tokens + summary.total_output_tokens).toLocaleString()} sub={`${summary.total_input_tokens.toLocaleString()} in / ${summary.total_output_tokens.toLocaleString()} out`} />
              <StatTile label="Total cost" value={fmtEur(summary.total_cost_eur)} sub={`avg ${fmtEur(summary.avg_cost_eur_per_generation)}/generation`} />
            </div>

            <div className="chart-grid" style={{ marginTop: 16 }}>
              <div className="chart-card">
                <h3>Latency per generation (s)</h3>
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={latencyData}>
                    <CartesianGrid stroke="var(--gridline)" vertical={false} />
                    <XAxis dataKey="idx" stroke="var(--text-muted)" fontSize={11} tickLine={false} />
                    <YAxis stroke="var(--text-muted)" fontSize={11} tickLine={false} width={32} />
                    <Tooltip content={<ChartTooltip />} />
                    <Line type="monotone" dataKey="latency" name="Latency (s)" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-card">
                <h3>Tokens per generation</h3>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={tokenData}>
                    <CartesianGrid stroke="var(--gridline)" vertical={false} />
                    <XAxis dataKey="idx" stroke="var(--text-muted)" fontSize={11} tickLine={false} />
                    <YAxis stroke="var(--text-muted)" fontSize={11} tickLine={false} width={40} />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="input" name="Input tokens" fill="var(--series-1)" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="output" name="Output tokens" fill="var(--series-2)" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}
      </div>

      <div className="section">
        <h2>Dependency &amp; dead-code alerts</h2>
        <AlertsPanel alerts={report?.alerts} />
      </div>

      <div className="section">
        <h2>Improvement suggestions</h2>
        <SuggestionsPanel suggestions={report?.improvement_suggestions} />
      </div>

      {report?.metrics_commentary && (
        <div className="section">
          <h2>Evaluator commentary</h2>
          <div className="commentary">{report.metrics_commentary}</div>
        </div>
      )}

      {records.length > 0 && (
        <div className="section">
          <h2>Recent generations</h2>
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Sender</th>
                <th>Receiver</th>
                <th>Model</th>
                <th>Tokens</th>
                <th>Cost</th>
                <th>Latency</th>
                <th>Repair</th>
              </tr>
            </thead>
            <tbody>
              {records.slice(0, 20).map((r) => (
                <tr key={r.id}>
                  <td>{new Date(r.created_at).toLocaleString()}</td>
                  <td>{r.sender_company}</td>
                  <td>{r.receiver_company}</td>
                  <td>{r.model_name}</td>
                  <td>{r.total_tokens.toLocaleString()}</td>
                  <td>{fmtEur(r.cost_eur)}</td>
                  <td>{r.latency_seconds.toFixed(2)}s</td>
                  <td>{r.repair_pass_needed ? 'yes' : 'no'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
