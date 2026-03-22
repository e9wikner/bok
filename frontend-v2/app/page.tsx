'use client'

import { Header } from '@/components/Header'
import Link from 'next/link'

export default function Home() {
  return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-8">Översikt</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Kort 1: Verifikationer */}
          <Link href="/vouchers">
            <div className="bg-white p-6 rounded-lg shadow hover:shadow-lg transition cursor-pointer">
              <h3 className="text-xl font-bold mb-2">📝 Verifikationer</h3>
              <p className="text-gray-600 mb-4">Se och korrigera alla bokförda verifikationer</p>
              <p className="text-blue-600 font-semibold">Visa →</p>
            </div>
          </Link>

          {/* Kort 2: Konton */}
          <Link href="/accounts">
            <div className="bg-white p-6 rounded-lg shadow hover:shadow-lg transition cursor-pointer">
              <h3 className="text-xl font-bold mb-2">📊 Kontoplan</h3>
              <p className="text-gray-600 mb-4">Hantera konton och följ saldon</p>
              <p className="text-blue-600 font-semibold">Visa →</p>
            </div>
          </Link>

          {/* Kort 3: AI-lärande */}
          <Link href="/learning">
            <div className="bg-white p-6 rounded-lg shadow hover:shadow-lg transition cursor-pointer">
              <h3 className="text-xl font-bold mb-2">🤖 AI-lärande</h3>
              <p className="text-gray-600 mb-4">Se regler som AI har lärt sig från dina korrigeringar</p>
              <p className="text-blue-600 font-semibold">Visa →</p>
            </div>
          </Link>

          {/* Kort 4: Rapporter */}
          <Link href="/reports">
            <div className="bg-white p-6 rounded-lg shadow hover:shadow-lg transition cursor-pointer">
              <h3 className="text-xl font-bold mb-2">📈 Rapporter</h3>
              <p className="text-gray-600 mb-4">Årsredovisning, K2, och finansiell analys</p>
              <p className="text-blue-600 font-semibold">Visa →</p>
            </div>
          </Link>
        </div>
      </div>
    </>
  )
}
