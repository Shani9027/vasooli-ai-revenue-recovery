import { useState, useEffect } from 'react'
import { API_BASE } from '../api'

export default function Dashboard({ batchId }) {
  const [batchInfo, setBatchInfo] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (batchId) {
      fetchBatchInfo()
    }
  }, [batchId])

  const fetchBatchInfo = async () => {
    setLoading(true)
    try {
      const response = await fetch(`${API_BASE}/api/batches/${batchId}`)
      if (!response.ok) return
      const data = await response.json()
      setBatchInfo(data)
    } catch (err) {
      console.error('Failed to fetch batch info:', err)
    } finally {
      setLoading(false)
    }
  }

  if (!batchId) {
    return (
      <div className="text-center py-12">
        <p className="text-gray-600 text-lg">Create a batch to get started</p>
      </div>
    )
  }

  if (loading) {
    return <div className="text-center py-12">Loading...</div>
  }

  if (!batchInfo) {
    return <div className="text-center py-12">No batch data available</div>
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      <div className="bg-white p-6 rounded-lg shadow">
        <div className="text-gray-600 text-sm font-medium">Total Invoices</div>
        <div className="text-3xl font-bold text-blue-600 mt-2">{batchInfo.total_invoices}</div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow">
        <div className="text-gray-600 text-sm font-medium">Revenue at Risk</div>
        <div className="text-3xl font-bold text-orange-600 mt-2">
          ₹{(batchInfo.revenue_at_risk / 100000).toFixed(1)}L
        </div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow">
        <div className="text-gray-600 text-sm font-medium">Recovered</div>
        <div className="text-3xl font-bold text-green-600 mt-2">
          ₹{(batchInfo.revenue_recovered / 100000).toFixed(1)}L
        </div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow">
        <div className="text-gray-600 text-sm font-medium">Recovery Rate</div>
        <div className="text-3xl font-bold text-green-600 mt-2">
          {batchInfo.recovery_rate.toFixed(1)}%
        </div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow">
        <div className="text-gray-600 text-sm font-medium">Batch Status</div>
        <div className="text-xl font-bold text-blue-600 mt-2 uppercase">{batchInfo.status}</div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow">
        <div className="text-gray-600 text-sm font-medium">Run Type</div>
        <div className="text-xl font-bold text-blue-600 mt-2">{batchInfo.run_type}</div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow">
        <div className="text-gray-600 text-sm font-medium">Created</div>
        <div className="text-sm font-mono mt-2">
          {new Date(batchInfo.started_at).toLocaleString()}
        </div>
      </div>

      <div className="bg-white p-6 rounded-lg shadow">
        <div className="text-gray-600 text-sm font-medium">Batch ID</div>
        <div className="text-xs font-mono mt-2 break-all text-blue-600">{batchInfo.id}</div>
      </div>
    </div>
  )
}
