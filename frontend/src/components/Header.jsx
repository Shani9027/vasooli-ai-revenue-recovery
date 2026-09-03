export default function Header() {
  return (
    <header className="bg-gradient-to-r from-blue-600 to-blue-800 text-white shadow-lg">
      <div className="container mx-auto px-4 py-6 flex justify-between items-center flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold">Vasooli</h1>
          <p className="text-blue-100 mt-1">AI-Powered B2B Revenue Recovery Agent</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-3 py-1 bg-white bg-opacity-10 border border-white border-opacity-20 rounded-full text-xs font-medium">
            Track 03: AI Revenue Recovery
          </span>
          <span className="px-3 py-1 bg-purple-500 bg-opacity-30 border border-purple-300 rounded-full text-xs font-medium flex items-center gap-1">
            ⚡ Razorpay Test Mode
          </span>
        </div>
      </div>
    </header>
  )
}
