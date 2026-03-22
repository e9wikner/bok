'use client'

import { Header } from '@/components/Header'
import { useLearningRules } from '@/hooks/useVouchers'

export default function LearningPage() {
  const { data, isLoading, error } = useLearningRules()
  const rules = data?.rules || []

  if (isLoading) return <div className="p-4">Laddar AI-regler...</div>
  if (error) return <div className="p-4 text-red-600">Fel vid hämtning av regler</div>

  return (
    <>
      <Header />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-6">🤖 AI-Lärande</h2>

        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-600 mb-6">
            Dessa regler har skapats baserat på dina korrigeringar av AI-genererade verifikationer.
            AI använder dessa för att förbättra framtida bokföringar.
          </p>

          {rules.length === 0 ? (
            <p className="text-gray-500">Inga regler ännu. Börja korrigera verifikationer för att träna AI:n!</p>
          ) : (
            <table className="w-full border-collapse border border-gray-300">
              <thead className="bg-gray-100">
                <tr>
                  <th className="border border-gray-300 px-4 py-2 text-left">Mönster</th>
                  <th className="border border-gray-300 px-4 py-2 text-left">Värde</th>
                  <th className="border border-gray-300 px-4 py-2 text-center">Konto</th>
                  <th className="border border-gray-300 px-4 py-2 text-right">Confidence</th>
                  <th className="border border-gray-300 px-4 py-2 text-center">Använd</th>
                  <th className="border border-gray-300 px-4 py-2 text-center">Status</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule: any) => (
                  <tr key={rule.id} className="hover:bg-gray-50">
                    <td className="border border-gray-300 px-4 py-2">{rule.pattern_type}</td>
                    <td className="border border-gray-300 px-4 py-2 font-mono text-sm">{rule.pattern_value}</td>
                    <td className="border border-gray-300 px-4 py-2 text-center font-semibold">
                      {rule.corrected_account}
                    </td>
                    <td className="border border-gray-300 px-4 py-2 text-right">
                      <span className={`px-2 py-1 rounded text-sm ${
                        rule.confidence > 0.8 ? 'bg-green-100 text-green-700' :
                        rule.confidence > 0.5 ? 'bg-yellow-100 text-yellow-700' :
                        'bg-red-100 text-red-700'
                      }`}>
                        {(rule.confidence * 100).toFixed(0)}%
                      </span>
                    </td>
                    <td className="border border-gray-300 px-4 py-2 text-center">{rule.usage_count}</td>
                    <td className="border border-gray-300 px-4 py-2 text-center">
                      {rule.is_golden ? (
                        <span className="text-green-600">✅ Bekräftad</span>
                      ) : (
                        <span className="text-yellow-600">⚠️ Lärd</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="mt-6 p-4 bg-blue-50 rounded border border-blue-200">
            <h3 className="font-bold mb-2">💡 Hur det fungerar:</h3>
            <ol className="list-decimal list-inside text-sm text-gray-700 space-y-1">
              <li>AI föreslår ett konto för en transaktion</li>
              <li>Om det är fel, korrigerar du det och väljer "Lär AI:n av detta"</li>
              <li>AI analyserar skillnaden och skapar en regel</li>
              <li>Nästa gång AI ser liknande transaktioner använder det den nya regeln</li>
              <li>Ju fler korrektioner, desto bättre blir AI:n</li>
            </ol>
          </div>
        </div>
      </div>
    </>
  )
}
