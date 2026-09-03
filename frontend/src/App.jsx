import { useState, useEffect } from 'react'
import Header from './components/Header'
import Dashboard from './components/Dashboard'
import CaseList from './components/CaseList'
import MetricsPanel from './components/MetricsPanel'
import Comparison from './components/Comparison'

function App() {
  const [batchId, setBatchId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [view, setView] = useState('dashboard') // dashboard, cases, metrics, comparison
  const [recoveryInProgress, setRecoveryInProgress] = useState(false)
  const [recoveryStatus, setRecoveryStatus] = useState(null)

  const handleCreateBatch = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch('/api/batches/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ num_invoices: 100, run_type: 'VASOOLI' })
      })
      const data = await response.json()
      setBatchId(data.batch_id)
      setRecoveryStatus(null)
      setError(null)
    } catch (err) {
      setError(`Failed to create batch: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleRunVasooli = async () => {
    if (!batchId) {
      setError('Create a batch first')
      return
    }
    setRecoveryInProgress(true)
    setRecoveryStatus('Running Vasooli recovery...')
    try {
      const response = await fetch(`/api/batches/${batchId}/vasooli-recovery`, {
        method: 'POST'
      })
      const data = await response.json()
      setRecoveryStatus(`✅ Vasooli complete: ${data.successful}/${data.total_cases} cases recovered ₹${(data.revenue_recovered / 100000).toFixed(2)}L`)
    } catch (err) {
      setError(`Failed to run Vasooli: ${err.message}`)
    } finally {
      setRecoveryInProgress(false)
    }
  }

  const handleRunBaseline = async () => {
    setRecoveryInProgress(true)
    setRecoveryStatus('Running baseline recovery...')
    try {
      const response = await fetch(`/api/batches/${batchId || 'default'}/baseline-recovery`, {
        method: 'POST'
      })
      const data = await response.json()
      setRecoveryStatus(`✅ Baseline complete: ${data.successful}/${data.total_cases} cases recovered ₹${(data.revenue_recovered / 100000).toFixed(2)}L`)
      setView('comparison')
    } catch (err) {
      setError(`Failed to run baseline: ${err.message}`)
    } finally {
      setRecoveryInProgress(false)
    }
  }

  const handleReset = async () => {
    setLoading(true)
    setError(null)
    try {
      await fetch('/api/admin/reset', { method: 'POST' })
      setBatchId(null)
      setRecoveryStatus(null)
      setError(null)
    } catch (err) {
      setError(`Failed to reset: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      
      <div className="container mx-auto px-4 py-8">
        {error && (
          <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}

        {recoveryStatus && (
          <div className="mb-4 p-4 bg-blue-100 border border-blue-400 text-blue-700 rounded">
            {recoveryStatus}
          </div>
        )}

        <div className="mb-6 flex gap-4 items-center flex-wrap">
          <button
            onClick={handleCreateBatch}
            disabled={loading || recoveryInProgress}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
          >
            {loading ? 'Creating...' : '📋 Create Batch (100)'}
          </button>

          <button
            onClick={handleRunVasooli}
            disabled={loading || recoveryInProgress || !batchId}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400"
          >
            {recoveryInProgress ? '⏳ Vasooli...' : '🤖 Run Vasooli'}
          </button>

          <button
            onClick={handleRunBaseline}
            disabled={loading || recoveryInProgress || !batchId}
            className="px-4 py-2 bg-orange-600 text-white rounded hover:bg-orange-700 disabled:bg-gray-400"
          >
            {recoveryInProgress ? '⏳ Baseline...' : '📊 Run Baseline'}
          </button>

          <button
            onClick={handleReset}
            disabled={loading || recoveryInProgress}
            className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:bg-gray-400"
          >
            🔄 Reset
          </button>

          {batchId && (
            <span className="text-sm font-mono bg-gray-200 px-3 py-1 rounded">
              Batch: {batchId.substring(0, 12)}...
            </span>
          )}
        </div>

        <div className="mb-6 flex gap-4 border-b flex-wrap">
          <button
            onClick={() => setView('dashboard')}
            className={`px-4 py-2 font-medium ${view === 'dashboard' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'}`}
          >
            📊 Dashboard
          </button>
          <button
            onClick={() => setView('cases')}
            className={`px-4 py-2 font-medium ${view === 'cases' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'}`}
          >
            📋 Cases
          </button>
          <button
            onClick={() => setView('metrics')}
            className={`px-4 py-2 font-medium ${view === 'metrics' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'}`}
          >
            📈 Metrics
          </button>
          <button
            onClick={() => setView('comparison')}
            className={`px-4 py-2 font-medium ${view === 'comparison' ? 'border-b-2 border-blue-600 text-blue-600' : 'text-gray-600'}`}
          >
            ⚖️ Comparison
          </button>
        </div>

        {view === 'dashboard' && <Dashboard batchId={batchId} />}
        {view === 'cases' && <CaseList />}
        {view === 'metrics' && <MetricsPanel />}
        {view === 'comparison' && <Comparison />}
      </div>
    </div>
  )
}

export default App
