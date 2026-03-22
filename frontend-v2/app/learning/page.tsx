'use client'

import { Header } from '@/components/Header'
import { useLearningRules } from '@/hooks/useVouchers'

export const dynamic = 'force-dynamic'

export default function LearningPage() {
  const { data, isLoading, error } = useLearningRules()
  const rules = data?.rules || []

  if (isLoading) return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">Laddar AI-lärande regler...</div>
    </>
  )

  if (error) return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8 text-red-600">Fel vid hämtning av regler</div>
    </>
  )

  const sortedRules = [...rules].sort((a, b) => b.confidence - a.confidence)

  return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-6">🤖 AI-Lärande Regler</h2>

        {rules.length === 0 ? (
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
            <p className="text-gray-700">
              Inga inlärda regler ännu. Börja genom att korrigera AI-bokförda verifikationer.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {sortedRules.map((rule: any) => (
              <div key={rule.id} className="bg-white border border-gray-300 rounded-lg p-4">
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h3 className="font-bold text-lg">
                      {rule.pattern_value || 'Pattern'}
                    </h3>
                    <p className="text-gray-600">
                      Bokför på konto <span className="font-mono font-bold">{rule.corrected_account}</span>
                    </p>
                  </div>
                  <div className="text-right">
                    <div className="text-sm text-gray-600">Säkerhet</div>
                    <div className="text-xl font-bold">
                      {(rule.confidence * 100).toFixed(0)}%
                    </div>
                  </div>
                </div>

                <div className="flex gap-4 text-sm text-gray-600 border-t pt-3">
                  <div>
                    <span className="font-semibold">Använd {rule.usage_count}</span> gånger
                  </div>
                  <div>
                    <span className="font-semibold">Typ:</span> {rule.pattern_type}
                  </div>
                  {rule.is_golden && (
                    <div className="text-green-600">
                      ✅ Bekräftad
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  )
}
