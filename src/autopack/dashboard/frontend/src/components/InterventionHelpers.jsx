import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'

const API_BASE = 'http://localhost:8000'

export default function InterventionHelpers({ runId }) {
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const { data: runStatus } = useQuery({
    queryKey: ['runStatus', runId],
    queryFn: async () => {
      const response = await axios.get(`${API_BASE}/dashboard/runs/${runId}/status`)
      return response.data
    },
    enabled: !!runId,
  })

  const contextBlock = runStatus ? `## Current Autopack Run Context

Run ID: ${runStatus.run_id}
State: ${runStatus.state}
Current: ${runStatus.current_tier_name || 'N/A'} / ${runStatus.current_phase_name || 'N/A'}
Progress: ${Math.round(runStatus.percent_complete)}%
Tokens: ${(runStatus.tokens_used / 1000000).toFixed(2)}M / ${(runStatus.token_cap / 1000000).toFixed(0)}M
` : 'No run selected'

  const copyToClipboard = () => {
    navigator.clipboard.writeText(contextBlock)
    alert('Context copied to clipboard!')
  }

  const submitNote = async () => {
    if (!note.trim()) return

    setSubmitting(true)
    try {
      await axios.post(`${API_BASE}/dashboard/human-notes`, {
        note: note.trim(),
        run_id: runId,
      })
      alert('Note added successfully!')
      setNote('')
    } catch (error) {
      alert('Error submitting note: ' + error.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div>
      <div style={{ marginBottom: '12px' }}>
        <strong style={{ fontSize: '13px' }}>Run Context (copy to Claude/Cursor)</strong>
      </div>
      <div className="context-block">{contextBlock}</div>
      <button onClick={copyToClipboard} style={{ marginBottom: '20px', width: '100%' }}>
        Copy Context to Clipboard
      </button>

      <div style={{ marginBottom: '12px' }}>
        <strong style={{ fontSize: '13px' }}>Human Notes</strong>
      </div>
      <textarea
        className="notes-textarea"
        placeholder="Add notes for Autopack to read (e.g., 'Skip UI tests for this run')"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <button
        onClick={submitNote}
        disabled={!note.trim() || submitting}
        style={{ marginTop: '8px', width: '100%' }}
      >
        {submitting ? 'Submitting...' : 'Submit Note'}
      </button>
    </div>
  )
}
