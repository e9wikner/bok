'use client'

import { Header } from '@/components/Header'
import { useState } from 'react'
import { useIncomeStatement, useBalanceSheet, useTrialBalance } from '@/hooks/useReports'

export const dynamic = 'force-dynamic'

export default function ReportsPage() {
  const [activeReport, setActiveReport] = useState<'income' | 'balance' | 'trial' | null>(null)
  const [year, setYear] = useState(new Date().getFullYear())

  const incomeData = useIncomeStatement(activeReport === 'income' ? year : undefined)
  const balanceData = useBalanceSheet(activeReport === 'balance' ? year : undefined)
  const trialData = useTrialBalance(activeReport === 'trial' ? year : undefined)

  const currentYear = new Date().getFullYear()
  const years = Array.from({ length: 5 }, (_, i) => currentYear - i)

  return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-6">Rapporter</h2>

        {/* Rapportöversikt */}
        {!activeReport && (
          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => setActiveReport('income')}
              className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition text-left"
            >
              <h3 className="text-lg font-bold mb-2">📊 Resultaträkning</h3>
              <p className="text-gray-600 text-sm">Visa intäkter och kostnader för vald period</p>
            </button>
            <button
              onClick={() => setActiveReport('balance')}
              className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition text-left"
            >
              <h3 className="text-lg font-bold mb-2">💰 Balansräkning</h3>
              <p className="text-gray-600 text-sm">Visa tillgångar, skulder och eget kapital</p>
            </button>
            <button
              onClick={() => setActiveReport('trial')}
              className="bg-white rounded-lg shadow p-6 hover:shadow-lg transition text-left"
            >
              <h3 className="text-lg font-bold mb-2">📑 Råbalans</h3>
              <p className="text-gray-600 text-sm">Trial balance för alla konton</p>
            </button>
          </div>
        )}

        {/* Resultaträkning */}
        {activeReport === 'income' && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-2xl font-bold">Resultaträkning</h3>
              <button
                onClick={() => setActiveReport(null)}
                className="text-gray-600 hover:text-gray-900"
              >
                ← Tillbaka
              </button>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-semibold mb-2">År</label>
              <select
                value={year}
                onChange={(e) => setYear(parseInt(e.target.value))}
                className="border border-gray-300 rounded px-3 py-2"
              >
                {years.map(y => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>

            {incomeData.isLoading && <p>Laddar resultaträkning...</p>}
            {incomeData.error && <p className="text-red-600">Fel vid hämtning av data</p>}

            {incomeData.data && (
              <table className="w-full border-collapse border border-gray-300">
                <tbody>
                  <tr className="bg-blue-50">
                    <td className="border border-gray-300 px-4 py-2 font-bold">Intäkter</td>
                    <td className="border border-gray-300 px-4 py-2 text-right font-bold">
                      {incomeData.data.revenue?.toLocaleString('sv-SE')} kr
                    </td>
                  </tr>
                  <tr className="bg-red-50">
                    <td className="border border-gray-300 px-4 py-2 font-bold">Kostnader</td>
                    <td className="border border-gray-300 px-4 py-2 text-right font-bold">
                      {incomeData.data.costs?.toLocaleString('sv-SE')} kr
                    </td>
                  </tr>
                  <tr className="bg-green-50">
                    <td className="border border-gray-300 px-4 py-2 font-bold">Resultat</td>
                    <td className="border border-gray-300 px-4 py-2 text-right font-bold text-lg">
                      {incomeData.data.profit?.toLocaleString('sv-SE')} kr
                    </td>
                  </tr>
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* Balansräkning */}
        {activeReport === 'balance' && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-2xl font-bold">Balansräkning</h3>
              <button
                onClick={() => setActiveReport(null)}
                className="text-gray-600 hover:text-gray-900"
              >
                ← Tillbaka
              </button>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-semibold mb-2">År</label>
              <select
                value={year}
                onChange={(e) => setYear(parseInt(e.target.value))}
                className="border border-gray-300 rounded px-3 py-2"
              >
                {years.map(y => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>

            {balanceData.isLoading && <p>Laddar balansräkning...</p>}
            {balanceData.error && <p className="text-red-600">Fel vid hämtning av data</p>}

            {balanceData.data && (
              <div className="grid grid-cols-2 gap-8">
                <div>
                  <h4 className="text-lg font-bold mb-3">Tillgångar</h4>
                  <table className="w-full border-collapse border border-gray-300">
                    <tbody>
                      <tr>
                        <td className="border border-gray-300 px-4 py-2">Omsättningstillgångar</td>
                        <td className="border border-gray-300 px-4 py-2 text-right">
                          {balanceData.data.current_assets?.toLocaleString('sv-SE')} kr
                        </td>
                      </tr>
                      <tr>
                        <td className="border border-gray-300 px-4 py-2">Anläggningstillgångar</td>
                        <td className="border border-gray-300 px-4 py-2 text-right">
                          {balanceData.data.fixed_assets?.toLocaleString('sv-SE')} kr
                        </td>
                      </tr>
                      <tr className="bg-blue-50 font-bold">
                        <td className="border border-gray-300 px-4 py-2">TOTALT</td>
                        <td className="border border-gray-300 px-4 py-2 text-right">
                          {balanceData.data.total_assets?.toLocaleString('sv-SE')} kr
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div>
                  <h4 className="text-lg font-bold mb-3">Skulder & Eget kapital</h4>
                  <table className="w-full border-collapse border border-gray-300">
                    <tbody>
                      <tr>
                        <td className="border border-gray-300 px-4 py-2">Kortfristiga skulder</td>
                        <td className="border border-gray-300 px-4 py-2 text-right">
                          {balanceData.data.current_liabilities?.toLocaleString('sv-SE')} kr
                        </td>
                      </tr>
                      <tr>
                        <td className="border border-gray-300 px-4 py-2">Långfristiga skulder</td>
                        <td className="border border-gray-300 px-4 py-2 text-right">
                          {balanceData.data.long_term_liabilities?.toLocaleString('sv-SE')} kr
                        </td>
                      </tr>
                      <tr>
                        <td className="border border-gray-300 px-4 py-2">Eget kapital</td>
                        <td className="border border-gray-300 px-4 py-2 text-right">
                          {balanceData.data.equity?.toLocaleString('sv-SE')} kr
                        </td>
                      </tr>
                      <tr className="bg-green-50 font-bold">
                        <td className="border border-gray-300 px-4 py-2">TOTALT</td>
                        <td className="border border-gray-300 px-4 py-2 text-right">
                          {balanceData.data.total_liabilities?.toLocaleString('sv-SE')} kr
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Råbalans */}
        {activeReport === 'trial' && (
          <div className="bg-white rounded-lg shadow p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-2xl font-bold">Råbalans</h3>
              <button
                onClick={() => setActiveReport(null)}
                className="text-gray-600 hover:text-gray-900"
              >
                ← Tillbaka
              </button>
            </div>

            <div className="mb-4">
              <label className="block text-sm font-semibold mb-2">År</label>
              <select
                value={year}
                onChange={(e) => setYear(parseInt(e.target.value))}
                className="border border-gray-300 rounded px-3 py-2"
              >
                {years.map(y => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>

            {trialData.isLoading && <p>Laddar råbalans...</p>}
            {trialData.error && <p className="text-red-600">Fel vid hämtning av data</p>}

            {trialData.data && (
              <table className="w-full border-collapse border border-gray-300">
                <thead className="bg-gray-100">
                  <tr>
                    <th className="border border-gray-300 px-4 py-2 text-left">Konto</th>
                    <th className="border border-gray-300 px-4 py-2 text-right">Debet</th>
                    <th className="border border-gray-300 px-4 py-2 text-right">Kredit</th>
                  </tr>
                </thead>
                <tbody>
                  {trialData.data.accounts?.map((account: any) => (
                    <tr key={account.code} className="hover:bg-gray-50">
                      <td className="border border-gray-300 px-4 py-2">{account.code} - {account.name}</td>
                      <td className="border border-gray-300 px-4 py-2 text-right">
                        {account.debit?.toLocaleString('sv-SE')} kr
                      </td>
                      <td className="border border-gray-300 px-4 py-2 text-right">
                        {account.credit?.toLocaleString('sv-SE')} kr
                      </td>
                    </tr>
                  ))}
                  <tr className="bg-blue-50 font-bold">
                    <td className="border border-gray-300 px-4 py-2">TOTALT</td>
                    <td className="border border-gray-300 px-4 py-2 text-right">
                      {trialData.data.total_debit?.toLocaleString('sv-SE')} kr
                    </td>
                    <td className="border border-gray-300 px-4 py-2 text-right">
                      {trialData.data.total_credit?.toLocaleString('sv-SE')} kr
                    </td>
                  </tr>
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </>
  )
}
