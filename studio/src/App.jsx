import { useState } from 'react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function escapeAttr(str) {
  return String(str).replace(/[^#a-zA-Z0-9]/g, '')
}

function Brochure({ article, retrieval, metrics }) {
  const logoSlot = (name) => article.image_slots.find((s) => s.slot_name === name)
  const senderLogo = logoSlot('sender_logo')
  const receiverLogo = logoSlot('receiver_logo')
  const primary = escapeAttr(article.theme.primary_color) || '#1a1d23'
  const secondary = escapeAttr(article.theme.secondary_color) || '#4b5563'

  return (
    <div className="brochure">
      <div className="brochure-hero" style={{ background: `linear-gradient(135deg, ${primary}, ${secondary})` }}>
        {(senderLogo?.asset_ref || receiverLogo?.asset_ref) && (
          <div className="brochure-logos">
            {senderLogo?.asset_ref && <img src={`${API_URL}/${senderLogo.asset_ref}`} alt="sender logo" />}
            {receiverLogo?.asset_ref && <img src={`${API_URL}/${receiverLogo.asset_ref}`} alt="receiver logo" />}
          </div>
        )}
        <h1>{article.headline}</h1>
        <p>{article.subheadline}</p>
      </div>

      <div className="brochure-body">
        {article.body_sections.map((s, i) => (
          <div className="brochure-section" key={i}>
            <h3>{s.heading}</h3>
            <p>{s.text}</p>
          </div>
        ))}
      </div>

      {article.tables?.length > 0 && (
        <div className="brochure-tables">
          {article.tables.map((t, i) => (
            <div className="brochure-table-block" key={i}>
              <h4>{t.title}</h4>
              <table className="brochure-table">
                <thead>
                  <tr style={{ background: primary }}>
                    {t.headers.map((h, j) => (
                      <th key={j}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {t.rows.map((row, r) => (
                    <tr key={r}>
                      {row.map((cell, c) => (
                        <td key={c}>{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}

      <div className="brochure-cta-wrap">
        <span className="brochure-cta" style={{ background: primary }}>{article.cta}</span>
      </div>

      <div className="brochure-footer">
        <span>
          Receiver grounding: {retrieval.receiver_source === 'web_research' ? 'live web research' : 'uploaded document'}
          {' '}({retrieval.sender_chunks_used} sender + {retrieval.receiver_chunks_used} receiver source{retrieval.receiver_chunks_used === 1 ? '' : 's'})
        </span>
        <span>
          {metrics.total_tokens.toLocaleString()} tokens · {metrics.cost_eur < 0.01 ? metrics.cost_eur.toFixed(6) : metrics.cost_eur.toFixed(4)} EUR · {metrics.latency_seconds.toFixed(1)}s
        </span>
      </div>
    </div>
  )
}

export default function App() {
  const [senderCompany, setSenderCompany] = useState('')
  const [senderFile, setSenderFile] = useState(null)
  const [senderUploaded, setSenderUploaded] = useState(false)
  const [senderStatus, setSenderStatus] = useState(null)

  const [receiverCompany, setReceiverCompany] = useState('')
  const [receiverFile, setReceiverFile] = useState(null)
  const [receiverUploaded, setReceiverUploaded] = useState(false)
  const [receiverStatus, setReceiverStatus] = useState(null)

  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  async function doUpload(role, company, file, setStatus, setUploaded) {
    setStatus({ kind: 'pending', text: 'Uploading and parsing…' })
    const form = new FormData()
    form.append('files', file)
    try {
      const resp = await fetch(`${API_URL}/companies/${encodeURIComponent(company.trim())}/documents?role=${role}`, {
        method: 'POST',
        body: form,
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        setStatus({ kind: 'err', text: data.detail || `HTTP ${resp.status}` })
        setUploaded(false)
        return false
      }
      const doc = (data.documents || [])[0] || {}
      setStatus({ kind: 'ok', text: `Parsed — ${doc.chunk_count ?? '?'} chunks, ${doc.image_count ?? '?'} image(s).` })
      setUploaded(true)
      return true
    } catch (e) {
      setStatus({ kind: 'err', text: String(e) })
      setUploaded(false)
      return false
    }
  }

  async function uploadSender() {
    if (!senderCompany.trim() || !senderFile) {
      setSenderStatus({ kind: 'err', text: 'Enter a company name and choose a PDF.' })
      return false
    }
    return doUpload('sender', senderCompany, senderFile, setSenderStatus, setSenderUploaded)
  }

  async function uploadReceiver() {
    if (!receiverCompany.trim() || !receiverFile) {
      setReceiverStatus({ kind: 'err', text: 'Enter the target company name above and choose a PDF.' })
      return false
    }
    return doUpload('receiver', receiverCompany, receiverFile, setReceiverStatus, setReceiverUploaded)
  }

  async function generate() {
    if (!senderCompany.trim()) {
      setError('Enter your (sender) company name.')
      return
    }
    if (!receiverCompany.trim()) {
      setError('Enter the target (receiver) company name.')
      return
    }
    if (!prompt.trim()) {
      setError('Describe what you want.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      // Choosing a file doesn't upload it by itself — make sure anything
      // picked but not yet uploaded goes up before we generate. Track
      // readiness locally: state set inside uploadSender()/uploadReceiver()
      // won't be visible via senderUploaded/receiverUploaded until the next
      // render, so we can't re-read those closures below.
      let senderReady = senderUploaded
      if (senderFile && !senderUploaded) {
        senderReady = await uploadSender()
        if (!senderReady) {
          setError('Sender PDF upload failed — see the error under the upload field.')
          return
        }
      }
      if (!senderReady) {
        setError('Upload the sender PDF first.')
        return
      }
      if (receiverFile && !receiverUploaded) {
        const ok = await uploadReceiver()
        if (!ok) {
          setError('Receiver PDF upload failed — see the error under the upload field.')
          return
        }
      }
      const resp = await fetch(`${API_URL}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sender_company: senderCompany.trim(),
          receiver_company: receiverCompany.trim(),
          prompt: prompt.trim(),
        }),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) {
        setError(data.detail || `HTTP ${resp.status}`)
        return
      }
      setResult(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  const showResearchQuotaHint = error && /quota|RESOURCE_EXHAUSTED|rate-limit/i.test(error)

  return (
    <>
      <div className="page-header">
        <h1>marketing-app studio</h1>
        <p>Upload your materials, name the company you're pitching to, describe what you want — get a grounded, personalized marketing brochure.</p>
      </div>

      <div className="layout">
        <div>
          <div className="card">
            <h2>1. Your company (Sender)</h2>
            <p className="hint">Upload any PDF with your product/positioning info. Generate will upload it for you if you skip this button.</p>
            <label>Company name</label>
            <input type="text" value={senderCompany} onChange={(e) => setSenderCompany(e.target.value)} placeholder="e.g. NexusVisionAI" />
            <label>PDF</label>
            <input type="file" accept="application/pdf" onChange={(e) => { setSenderFile(e.target.files[0] || null); setSenderUploaded(false) }} />
            <button className="primary" onClick={uploadSender}>Upload sender materials</button>
            {senderStatus && <div className={`status-line ${senderStatus.kind}`}>{senderStatus.kind === 'pending' && <span className="spinner" />}{senderStatus.text}</div>}
          </div>

          <div className="card">
            <h2>2. Target company (Receiver)</h2>
            <p className="hint">Just type the name — we'll research them live via web search. No upload needed.</p>
            <label>Target company name</label>
            <input type="text" value={receiverCompany} onChange={(e) => setReceiverCompany(e.target.value)} placeholder="e.g. Contoso Logistics" />

            <details className="optional-block">
              <summary>Optional: upload a PDF for this company instead</summary>
              <p className="hint" style={{ marginTop: 8 }}>
                Use this if live research fails (e.g. search quota) or you want grounding on a specific document.
              </p>
              <label>PDF</label>
              <input type="file" accept="application/pdf" onChange={(e) => { setReceiverFile(e.target.files[0] || null); setReceiverUploaded(false) }} />
              <button className="secondary" style={{ marginTop: 10 }} onClick={uploadReceiver}>Upload receiver PDF</button>
              {receiverStatus && <div className={`status-line ${receiverStatus.kind}`}>{receiverStatus.kind === 'pending' && <span className="spinner" />}{receiverStatus.text}</div>}
              {receiverUploaded && <div className="status-line ok">Will ground on this document instead of live research.</div>}
            </details>
          </div>

          <div className="card">
            <h2>3. Describe what you want</h2>
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="e.g. Pitch our computer vision platform for reducing manual inspection costs, emphasize ROI." />
            <button className="primary" onClick={generate} disabled={loading}>
              {loading ? (<><span className="spinner" />Generating…</>) : 'Generate marketing material'}
            </button>
          </div>
        </div>

        <div>
          {result && (
            <div className="preview-toolbar">
              <button className="secondary" onClick={() => window.print()}>Print / Save as PDF</button>
            </div>
          )}

          {error && (
            <div className="error-box" style={{ marginBottom: 16 }}>
              <strong>Generation failed.</strong>
              <p style={{ margin: '8px 0 0' }}>{error}</p>
              {showResearchQuotaHint && (
                <p style={{ margin: '8px 0 0' }}>
                  This looks like Gemini's live-search grounding quota is exhausted (common on free-tier keys).
                  Open "Optional: upload a PDF for this company instead" above and retry with an uploaded document.
                </p>
              )}
            </div>
          )}

          {loading && (
            <div className="preview-empty">
              <span className="spinner" />
              Generating your marketing material — researching the receiver live can take a bit longer than a normal request.
            </div>
          )}

          {!loading && !error && !result && (
            <div className="preview-empty">Fill in the form and generate to see your personalized brochure here.</div>
          )}

          {!loading && result && (
            <Brochure article={result.article} retrieval={result.retrieval} metrics={result.metrics} />
          )}
        </div>
      </div>
    </>
  )
}
