import { useState, useEffect } from 'react'
import axios from 'axios'

export default function Comparison() {
  const [comparison, setComparison] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchComparison()
  }, [])

  const fetchComparison = async () => {
    try {
      setLoading(true)
      const response = await axios.get('/api/metrics/comparison')
      setComparison(response.data)
      setError(null)
    } catch (err) {
      setError(`Failed to load comparison: ${err.message}`)
      setComparison(null)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <div className="text-center py-8">Loading...</div>
  if (error) return <div className="text-red-600">{error}</div>
  if (!comparison) return <div>No comparison data available. Run both Vasooli and Baseline first.</div>

  const { vasooli, baseline, improvement_percentage_points, improvement_lift } = comparison

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-2xl font-bold mb-6">🤖 Vasooli vs Baseline Comparison</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {/* Vasooli */}
          <div className="bg-gradient-to-br from-green-50 to-green-100 border-2 border-green-500 rounded-lg p-6">
            <h3 className="text-lg font-bold text-green-800 mb-4">Vasooli (AI-Powered)</h3>
            <div className="space-y-3">
              <div>
                <div className="text-sm text-gray-600">Recovery Rate</div>
                <div className="text-3xl font-bold text-green-700">{vasooli.recovery_rate.toFixed(1)}%</div>
              </div>
              <div>
                <div className="text-sm text-gray-600">Revenue Recovered</div>
                <div className="text-2xl font-bold text-green-700">₹{(vasooli.revenue_recovered / 100000).toFixed(2)}L</div>
              </div>
              <div>
                <div className="text-sm text-gray-600">Cases Processed</div>
                <div className="text-xl font-bold text-green-700">{vasooli.total_cases}</div>
              </div>
            </div>
          </div>

          {/* Baseline */}
          <div className="bg-gradient-to-br from-orange-50 to-orange-100 border-2 border-orange-500 rounded-lg p-6">
            <h3 className="text-lg font-bold text-orange-800 mb-4">Baseline (One Reminder)</h3>
            <div className="space-y-3">
              <div>
                <div className="text-sm text-gray-600">Recovery Rate</div>
                <div className="text-3xl font-bold text-orange-700">{baseline.recovery_rate.toFixed(1)}%</div>
              </div>
              <div>
                <div className="text-sm text-gray-600">Revenue Recovered</div>
                <div className="text-2xl font-bold text-orange-700">₹{(baseline.revenue_recovered / 100000).toFixed(2)}L</div>
              </div>
              <div>
                <div className="text-sm text-gray-600">Cases Processed</div>
                <div className="text-xl font-bold text-orange-700">{baseline.total_cases}</div>
              </div>
            </div>
          </div>

          {/* Improvement */}
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 border-2 border-blue-500 rounded-lg p-6">
            <h3 className="text-lg font-bold text-blue-800 mb-4">📈 Improvement</h3>
            <div className="space-y-3">
              <div>
                <div className="text-sm text-gray-600">Recovery Lift</div>
                <div className={`text-3xl font-bold ${improvement_percentage_points >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {improvement_lift}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-600">Additional Revenue</div>
                <div className="text-2xl font-bold text-blue-700">
                  ₹{((vasooli.revenue_recovered - baseline.revenue_recovered) / 100000).toFixed(2)}L
                </div>
              </div>
              <div className="text-sm text-blue-700 font-semibold">
                {improvement_percentage_points >= 0 ? '✅ Vasooli Wins!' : '⚠️ Baseline Wins'}
              </div>
            </div>
          </div>
        </div>

        {/* Visual comparison */}
        <div className="bg-gray-50 rounded-lg p-6">
          <h3 className="font-bold mb-4">Recovery Rate Comparison</h3>
          <div className="space-y-4">
            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium">Vasooli</span>
                <span className="text-sm font-bold">{vasooli.recovery_rate.toFixed(1)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-8 overflow-hidden">
                <div
                  className="bg-green-500 h-full transition-all duration-500"
                  style={{ width: `${Math.min(vasooli.recovery_rate, 100)}%` }}
                ></div>
              </div>
            </div>

            <div>
              <div className="flex justify-between mb-2">
                <span className="text-sm font-medium">Baseline</span>
                <span className="text-sm font-bold">{baseline.recovery_rate.toFixed(1)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-8 overflow-hidden">
                <div
                  className="bg-orange-500 h-full transition-all duration-500"
                  style={{ width: `${Math.min(baseline.recovery_rate, 100)}%` }}
                ></div>
              </div>
            </div>
          </div>
        </div>

        {/* Summary */}
        <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="font-bold text-blue-900 mb-3">📊 Summary</h3>
          <p className="text-blue-800">
            Vasooli achieved a <strong>{vasooli.recovery_rate.toFixed(1)}%</strong> recovery rate compared to the baseline's <strong>{baseline.recovery_rate.toFixed(1)}%</strong>, 
            a difference of <strong>{improvement_lift}</strong>. The AI-powered approach recovered an additional <strong>₹{((vasooli.revenue_recovered - baseline.revenue_recovered) / 100000).toFixed(2)}L</strong> in revenue.
          </p>
        </div>
      </div>

      <button
        onClick={fetchComparison}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        🔄 Refresh Comparison
      </button>
    </div>
  )
}
