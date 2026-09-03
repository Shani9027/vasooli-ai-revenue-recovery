import { useState, useEffect } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'

export default function MetricsPanel() {
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchMetrics()
  }, [])

  const fetchMetrics = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/metrics/summary')
      const data = await response.json()
      setMetrics(data)
    } catch (err) {
      console.error('Failed to fetch metrics:', err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="text-center py-12">Loading metrics...</div>
  }

  if (!metrics) {
    return <div className="text-center py-12 text-gray-600">No metrics available</div>
  }

  // Prepare data for charts
  const riskLevelData = Object.entries(metrics.cases_by_risk_level).map(([level, count]) => ({
    name: level,
    value: count
  }))

  const statusData = Object.entries(metrics.cases_by_status).map(([status, count]) => ({
    name: status,
    value: count
  }))

  const promiseData = [
    { name: 'Kept', value: metrics.promise_kept },
    { name: 'Broken', value: metrics.promise_broken },
    { name: 'Pending', value: metrics.promise_count - metrics.promise_kept - metrics.promise_broken }
  ]

  const COLORS = ['#10b981', '#ef4444', '#f59e0b', '#6366f1', '#8b5cf6', '#ec4899']

  return (
    <div className="space-y-8">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white p-6 rounded-lg shadow">
          <div className="text-gray-600 text-sm font-medium">Total Invoices</div>
          <div className="text-3xl font-bold text-blue-600 mt-2">{metrics.total_invoices}</div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <div className="text-gray-600 text-sm font-medium">Revenue at Risk</div>
          <div className="text-3xl font-bold text-orange-600 mt-2">
            ₹{(metrics.revenue_at_risk / 100000).toFixed(1)}L
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <div className="text-gray-600 text-sm font-medium">Revenue Recovered</div>
          <div className="text-3xl font-bold text-green-600 mt-2">
            ₹{(metrics.revenue_recovered / 100000).toFixed(1)}L
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <div className="text-gray-600 text-sm font-medium">Recovery Rate</div>
          <div className="text-3xl font-bold text-green-600 mt-2">{metrics.recovery_rate.toFixed(1)}%</div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <div className="text-gray-600 text-sm font-medium">Escalated Cases</div>
          <div className="text-3xl font-bold text-red-600 mt-2">{metrics.escalated_count}</div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <div className="text-gray-600 text-sm font-medium">Stopped Cases</div>
          <div className="text-3xl font-bold text-gray-600 mt-2">{metrics.stopped_count}</div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <div className="text-gray-600 text-sm font-medium">Promises Made</div>
          <div className="text-3xl font-bold text-blue-600 mt-2">{metrics.promise_count}</div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <div className="text-gray-600 text-sm font-medium">Promises Kept</div>
          <div className="text-3xl font-bold text-green-600 mt-2">{metrics.promise_kept}</div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Risk Level Distribution */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-bold mb-4">Cases by Risk Level</h3>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie
                data={riskLevelData}
                cx="50%"
                cy="50%"
                labelLine={false}
                label={({ name, value }) => `${name}: ${value}`}
                outerRadius={80}
                fill="#8884d8"
                dataKey="value"
              >
                {riskLevelData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Status Distribution */}
        <div className="bg-white p-6 rounded-lg shadow">
          <h3 className="text-lg font-bold mb-4">Cases by Status</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={statusData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#3b82f6" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Promise Status */}
      <div className="bg-white p-6 rounded-lg shadow">
        <h3 className="text-lg font-bold mb-4">Promise-to-Pay Status</h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={promiseData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="value" fill="#10b981" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
