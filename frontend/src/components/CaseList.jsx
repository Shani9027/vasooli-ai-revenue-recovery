import { useState, useEffect } from 'react'
import axios from 'axios'
import { API_BASE } from '../api'

export default function CaseList() {
  const [cases, setCases] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedCase, setSelectedCase] = useState(null)
  const [auditTrail, setAuditTrail] = useState([])
  const [loadingAudit, setLoadingAudit] = useState(false)
  const [promises, setPromises] = useState([])
  const [loadingPromises, setLoadingPromises] = useState(false)

  useEffect(() => {
    fetchCases()
  }, [])

  const fetchCases = async () => {
    setLoading(true)
    try {
      const response = await axios.get(`${API_BASE}/api/cases?limit=100`)
      setCases(response.data)
    } catch (err) {
      console.error('Failed to fetch cases:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchAuditTrail = async (caseId) => {
    setLoadingAudit(true)
    try {
      const response = await axios.get(`${API_BASE}/api/cases/${caseId}/audit`)
      setAuditTrail(response.data)
    } catch (err) {
      console.error('Failed to fetch audit trail:', err)
      setAuditTrail([])
    } finally {
      setLoadingAudit(false)
    }
  }

  const fetchPromises = async (caseId) => {
    setLoadingPromises(true)
    try {
      const response = await axios.get(`${API_BASE}/api/cases/${caseId}/promises`)
      setPromises(response.data || [])
    } catch (err) {
      console.error('Failed to fetch promises:', err)
      setPromises([])
    } finally {
      setLoadingPromises(false)
    }
  }

  const handleViewCase = (caseItem) => {
    setSelectedCase(caseItem)
    fetchAuditTrail(caseItem.id)
    fetchPromises(caseItem.id)
  }

  if (loading) {
    return <div className="text-center py-12">Loading cases...</div>
  }

  if (cases.length === 0) {
    return <div className="text-center py-12 text-gray-600">No cases available</div>
  }

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-100">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-900">Case ID</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-900">Invoice</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-900">Risk Level</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-900">Risk Score</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-900">Stage</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-900">Status</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-900">Recovered</th>
                <th className="px-6 py-3 text-left text-sm font-medium text-gray-900">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {cases.map((caseItem) => (
                <tr key={caseItem.id} className="hover:bg-gray-50">
                  <td className="px-6 py-3 text-sm font-mono text-blue-600">{caseItem.id.substring(0, 12)}</td>
                  <td className="px-6 py-3 text-sm font-mono">{caseItem.invoice_id.substring(0, 12)}</td>
                  <td className="px-6 py-3 text-sm">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      caseItem.risk_level === 'LOW' ? 'bg-green-100 text-green-800' :
                      caseItem.risk_level === 'MEDIUM' ? 'bg-yellow-100 text-yellow-800' :
                      caseItem.risk_level === 'HIGH' ? 'bg-red-100 text-red-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {caseItem.risk_level}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-sm text-right font-mono">{caseItem.risk_score?.toFixed(1) || 'N/A'}</td>
                  <td className="px-6 py-3 text-sm text-center font-medium">{caseItem.escalation_stage}</td>
                  <td className="px-6 py-3 text-sm">
                    <span className={`px-2 py-1 rounded text-xs font-medium ${
                      caseItem.status === 'ACTIVE' ? 'bg-blue-100 text-blue-800' :
                      caseItem.status === 'PAYMENT_RECEIVED' ? 'bg-green-100 text-green-800' :
                      caseItem.status === 'ESCALATED' ? 'bg-orange-100 text-orange-800' :
                      caseItem.status === 'HUMAN_REVIEW' ? 'bg-purple-100 text-purple-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {caseItem.status}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-sm text-right">₹{((caseItem.revenue_recovered || 0) / 100000).toFixed(2)}L</td>
                  <td className="px-6 py-3 text-sm">
                    <button
                      onClick={() => handleViewCase(caseItem)}
                      className="text-blue-600 hover:text-blue-900 font-medium"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selectedCase && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-gradient-to-r from-blue-600 to-blue-700 px-6 py-4 border-b flex justify-between items-center">
              <h2 className="text-lg font-bold text-white">📋 Case Details & Audit Trail</h2>
              <button
                onClick={() => setSelectedCase(null)}
                className="text-white hover:text-gray-200 text-2xl"
              >
                ×
              </button>
            </div>

            <div className="px-6 py-6 space-y-6">
              {/* Case Summary */}
              {(() => {
                const rzpSuccessEvent = auditTrail.find(
                  (e) =>
                    (e.actor === 'razorpay_test' || e.output_data?.provider === 'razorpay_test' || e.input_data?.provider === 'razorpay_test') &&
                    e.passed
                )
                const rzpFailedEvent = auditTrail.find(
                  (e) =>
                    (e.actor === 'razorpay_test' || e.output_data?.provider === 'razorpay_test' || e.input_data?.provider === 'razorpay_test') &&
                    !e.passed
                )
                const txId =
                  rzpSuccessEvent?.output_data?.transaction_id ||
                  rzpSuccessEvent?.metadata_info?.transaction_id ||
                  auditTrail.find((e) => e.output_data?.transaction_id)?.output_data?.transaction_id

                return (
                  <div>
                    <h3 className="text-lg font-bold mb-4 text-gray-900">Case Summary</h3>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="bg-gray-50 p-3 rounded">
                        <div className="text-xs text-gray-600">Case ID</div>
                        <div className="font-mono text-sm font-bold">{selectedCase.id}</div>
                      </div>
                      <div className="bg-gray-50 p-3 rounded">
                        <div className="text-xs text-gray-600">Invoice ID</div>
                        <div className="font-mono text-sm font-bold">{selectedCase.invoice_id}</div>
                      </div>
                      <div className="bg-gray-50 p-3 rounded">
                        <div className="text-xs text-gray-600">Risk Level</div>
                        <div className={`text-sm font-bold ${
                          selectedCase.risk_level === 'LOW' ? 'text-green-700' :
                          selectedCase.risk_level === 'MEDIUM' ? 'text-yellow-700' :
                          selectedCase.risk_level === 'HIGH' ? 'text-red-700' :
                          'text-gray-700'
                        }`}>{selectedCase.risk_level}</div>
                      </div>
                      <div className="bg-gray-50 p-3 rounded">
                        <div className="text-xs text-gray-600">Status</div>
                        <div className="text-sm font-bold text-blue-700">{selectedCase.status}</div>
                      </div>
                      <div className="bg-gray-50 p-3 rounded">
                        <div className="text-xs text-gray-600">Escalation Stage</div>
                        <div className="text-sm font-bold">{selectedCase.escalation_stage}/4</div>
                      </div>
                      <div className="bg-gray-50 p-3 rounded">
                        <div className="text-xs text-gray-600">Recovered</div>
                        <div className="text-sm font-bold text-green-700">₹{((selectedCase.revenue_recovered || 0) / 100000).toFixed(2)}L</div>
                      </div>
                      <div className="bg-gray-50 p-3 rounded">
                        <div className="text-xs text-gray-600">Recovery Provider</div>
                        <div className="mt-1">
                          {rzpSuccessEvent ? (
                            <span className="px-2 py-0.5 rounded text-xs font-bold bg-purple-100 text-purple-800 border border-purple-300 inline-flex items-center gap-1">
                              ⚡ razorpay_test
                            </span>
                          ) : rzpFailedEvent && selectedCase.status === 'PAYMENT_RECEIVED' ? (
                            <span className="px-2 py-0.5 rounded text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300 inline-flex items-center gap-1">
                              🤖 simulator (fallback)
                            </span>
                          ) : selectedCase.status === 'PAYMENT_RECEIVED' ? (
                            <span className="px-2 py-0.5 rounded text-xs font-bold bg-blue-100 text-blue-800 border border-blue-200 inline-flex items-center gap-1">
                              🤖 simulator
                            </span>
                          ) : (
                            <span className="text-xs text-gray-500 font-medium">Pending</span>
                          )}
                        </div>
                      </div>
                      <div className="bg-gray-50 p-3 rounded">
                        <div className="text-xs text-gray-600">Transaction ID</div>
                        <div className="font-mono text-xs font-bold text-purple-700 mt-1 truncate" title={txId || 'N/A'}>
                          {txId || <span className="text-gray-400 font-normal">N/A</span>}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })()}

              {/* Promise-to-Pay Records */}
              <div>
                <h3 className="text-lg font-bold mb-3 text-gray-900">🤝 Promise-to-Pay Records</h3>
                {loadingPromises ? (
                  <div className="text-center py-3 text-gray-600">Loading promises...</div>
                ) : promises.length === 0 ? (
                  <div className="p-3 bg-gray-50 border border-gray-200 rounded text-xs text-gray-500">
                    No promises recorded for this case yet.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {promises.map((p) => (
                      <div key={p.id} className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                        <div className="flex justify-between items-center mb-1">
                          <span className="font-mono text-xs font-semibold text-blue-900">{p.id}</span>
                          <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                            p.status === 'KEPT' ? 'bg-green-100 text-green-800' :
                            p.status === 'BROKEN' ? 'bg-red-100 text-red-800' :
                            p.status === 'RENEGOTIATED' ? 'bg-yellow-100 text-yellow-800' :
                            'bg-blue-100 text-blue-800'
                          }`}>
                            {p.status}
                          </span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-xs mb-2">
                          <div>
                            <span className="text-gray-500">Promised Amount: </span>
                            <span className="font-bold text-gray-900">₹{((p.promised_amount || 0) / 100000).toFixed(2)}L</span>
                          </div>
                          <div>
                            <span className="text-gray-500">Promised Date: </span>
                            <span className="font-bold text-gray-900">{p.promised_date || 'N/A'}</span>
                          </div>
                          <div>
                            <span className="text-gray-500">AI Confidence: </span>
                            <span className="font-bold text-gray-900">{((p.extraction_confidence || 0) * 100).toFixed(0)}%</span>
                          </div>
                        </div>
                        {p.promise_text && (
                          <div className="text-xs italic bg-white p-2 rounded border text-gray-700">
                            &quot;{p.promise_text}&quot;
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Audit Trail */}
              <div>
                <h3 className="text-lg font-bold mb-4 text-gray-900">📊 Audit Timeline</h3>
                {loadingAudit ? (
                  <div className="text-center py-4 text-gray-600">Loading audit trail...</div>
                ) : auditTrail.length === 0 ? (
                  <div className="text-center py-4 text-gray-600">No audit events recorded</div>
                ) : (
                  <div className="space-y-2 max-h-72 overflow-y-auto">
                    {auditTrail.map((event, idx) => {
                      const provider =
                        event.output_data?.provider ||
                        event.input_data?.provider ||
                        (event.actor === 'razorpay_test'
                          ? 'razorpay_test'
                          : event.actor === 'SIMULATOR'
                          ? 'simulator'
                          : null)
                      const eventTxId =
                        event.output_data?.transaction_id ||
                        event.metadata_info?.transaction_id
                      const errorMsg = event.output_data?.error

                      return (
                        <div
                          key={idx}
                          className={`p-3 rounded border-l-4 ${
                            event.passed
                              ? 'bg-green-50 border-green-500'
                              : 'bg-red-50 border-red-500'
                          }`}
                        >
                          <div className="flex justify-between items-start flex-wrap gap-2">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-semibold text-sm text-gray-900">
                                {event.event_type}
                              </span>
                              <span className="text-xs px-2 py-0.5 rounded font-mono bg-gray-200 text-gray-800">
                                {event.actor}
                              </span>
                              {provider === 'razorpay_test' && (
                                <span className="text-xs px-2 py-0.5 rounded font-bold bg-purple-100 text-purple-800 border border-purple-300">
                                  ⚡ razorpay_test
                                </span>
                              )}
                              {provider === 'simulator' && (
                                <span className="text-xs px-2 py-0.5 rounded font-medium bg-blue-100 text-blue-800 border border-blue-200">
                                  🤖 simulator
                                </span>
                              )}
                            </div>
                            <div className="text-xs text-gray-600">
                              {new Date(event.timestamp).toLocaleTimeString()}
                            </div>
                          </div>

                          <div className="text-xs text-gray-700 mt-1">{event.reason}</div>

                          {eventTxId && (
                            <div className="mt-2 text-xs font-mono bg-purple-50 text-purple-900 p-1.5 rounded border border-purple-200 flex items-center gap-1">
                              <span className="font-semibold text-purple-700">Reference ID:</span> {eventTxId}
                            </div>
                          )}

                          {errorMsg && (
                            <div className="mt-2 text-xs font-mono bg-red-100 text-red-800 p-1.5 rounded border border-red-200">
                              <span className="font-semibold">Failure Details:</span> {errorMsg}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>

          </div>
        </div>
      )}

      <button
        onClick={fetchCases}
        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
      >
        🔄 Refresh Cases
      </button>
    </div>
  )
}
