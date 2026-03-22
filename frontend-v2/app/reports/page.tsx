'use client'

import { Header } from '@/components/Header'

export default function ReportsPage() {
  return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-6">Rapporter</h2>

        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition">
            <h3 className="text-lg font-bold mb-2">📊 Resultaträkning</h3>
            <p className="text-gray-600 text-sm">Visa intäkter och kostnader för vald period</p>
          </div>
          <div className="bg-white rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition">
            <h3 className="text-lg font-bold mb-2">💰 Balansräkning</h3>
            <p className="text-gray-600 text-sm">Visa tillgångar, skulder och eget kapital</p>
          </div>
          <div className="bg-white rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition">
            <h3 className="text-lg font-bold mb-2">📈 Huvudbok</h3>
            <p className="text-gray-600 text-sm">Detaljvy av alla transaktioner per konto</p>
          </div>
          <div className="bg-white rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition">
            <h3 className="text-lg font-bold mb-2">📑 Råbalans</h3>
            <p className="text-gray-600 text-sm">Trial balance för alla konton</p>
          </div>
        </div>
      </div>
    </>
  )
}
