'use client'

import { Header } from '@/components/Header'
import { useVoucher } from '@/hooks/useVouchers'
import { useState } from 'react'
import { api } from '@/lib/api'
import Link from 'next/link'

export default function VoucherDetailPage({ params }: { params: { id: string } }) {
  const { data: voucher, isLoading, error } = useVoucher(params.id)
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [teachAI, setTeachAI] = useState(true)
  const [reason, setReason] = useState('')

  const handleSaveCorrection = async () => {
    setIsSaving(true)
    try {
      await api.recordCorrection(
        params.id,
        { rows: voucher?.rows },
        reason
      )
      alert('✅ Korrigering sparad! AI:n har lärt sig av detta.')
      setIsEditing(false)
      setReason('')
    } catch (err) {
      alert('❌ Fel vid sparande av korrigering')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) return <div className="p-4">Laddar verifikation...</div>
  if (error) return <div className="p-4 text-red-600">Fel vid hämtning av verifikation</div>
  if (!voucher) return <div className="p-4">Verifikation hittades inte</div>

  return (
    <>
      <Header />
      <div className="max-w-4xl mx-auto px-4 py-8">
        <Link href="/vouchers" className="text-blue-600 hover:underline mb-4 inline-block">
          ← Tillbaka till lista
        </Link>

        <div className="bg-white rounded-lg shadow p-6 space-y-6">
          <div>
            <h1 className="text-3xl font-bold">Verifikation #{voucher.voucher_number}</h1>
            <p className="text-gray-600 mt-2">{voucher.voucher_date}</p>
          </div>

          <div className="border-t pt-4">
            <h3 className="text-xl font-bold mb-4">Beskrivning</h3>
            <p className="text-gray-700">{voucher.description}</p>
            {voucher.ai_generated && (
              <p className="text-orange-600 mt-2 text-sm">🤖 Denna verifikation skapades av AI</p>
            )}
          </div>

          <div className="border-t pt-4">
            <h3 className="text-xl font-bold mb-4">Bokföringsrader</h3>
            <table className="w-full border-collapse border border-gray-300">
              <thead className="bg-gray-100">
                <tr>
                  <th className="border border-gray-300 px-4 py-2 text-left">Konto</th>
                  <th className="border border-gray-300 px-4 py-2 text-left">Kontonamn</th>
                  <th className="border border-gray-300 px-4 py-2 text-right">Debet</th>
                  <th className="border border-gray-300 px-4 py-2 text-right">Kredit</th>
                </tr>
              </thead>
              <tbody>
                {voucher.rows.map((row: any, idx: number) => (
                  <tr key={idx}>
                    <td className="border border-gray-300 px-4 py-2">{row.account_code}</td>
                    <td className="border border-gray-300 px-4 py-2">{row.account_name}</td>
                    <td className="border border-gray-300 px-4 py-2 text-right">
                      {row.debit ? row.debit.toLocaleString('sv-SE') : '-'}
                    </td>
                    <td className="border border-gray-300 px-4 py-2 text-right">
                      {row.credit ? row.credit.toLocaleString('sv-SE') : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Korrigeringsformulär */}
          {isEditing && (
            <div className="border-t pt-4 bg-blue-50 p-4 rounded">
              <h3 className="text-lg font-bold mb-4">Korrigera denna verifikation</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Anledning till korrigering</label>
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Förklara vad som behöver korrigeras..."
                    className="w-full border border-gray-300 rounded px-3 py-2"
                    rows={3}
                  />
                </div>

                <div className="flex items-center">
                  <input
                    type="checkbox"
                    id="teach-ai"
                    checked={teachAI}
                    onChange={(e) => setTeachAI(e.target.checked)}
                    className="rounded"
                  />
                  <label htmlFor="teach-ai" className="ml-2 text-sm">
                    ✅ Lär AI:n av denna korrigering (förbättrar framtida bokföring)
                  </label>
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={handleSaveCorrection}
                    disabled={isSaving}
                    className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50"
                  >
                    {isSaving ? 'Sparar...' : 'Spara korrigering'}
                  </button>
                  <button
                    onClick={() => setIsEditing(false)}
                    className="bg-gray-300 text-gray-900 px-4 py-2 rounded hover:bg-gray-400"
                  >
                    Avbryt
                  </button>
                </div>
              </div>
            </div>
          )}

          {!isEditing && voucher.status === 'posted' && (
            <button
              onClick={() => setIsEditing(true)}
              className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
            >
              Korrigera
            </button>
          )}
        </div>
      </div>
    </>
  )
}
