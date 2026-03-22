'use client'

import { Header } from '@/components/Header'

export default function ReportsPage() {
  return (
    <>
      <Header />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-6">Rapporter</h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-xl font-bold mb-4">📊 Resultaträkning</h3>
            <p className="text-gray-600 mb-4">Intäkter minus kostnader för räkenskapsperioden</p>
            <button className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
              Visa rapport
            </button>
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-xl font-bold mb-4">💰 Balansräkning</h3>
            <p className="text-gray-600 mb-4">Tillgångar, skulder och eget kapital</p>
            <button className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
              Visa rapport
            </button>
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-xl font-bold mb-4">📋 K2-rapport</h3>
            <p className="text-gray-600 mb-4">Årsredovisning för Swedish Tax Agency</p>
            <button className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
              Visa rapport
            </button>
          </div>

          <div className="bg-white p-6 rounded-lg shadow">
            <h3 className="text-xl font-bold mb-4">🔍 Råbalans</h3>
            <p className="text-gray-600 mb-4">Trial balance före kontering</p>
            <button className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
              Visa rapport
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
