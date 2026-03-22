'use client'

import { Header } from '@/components/Header'
import { CorrectionForm } from '@/components/CorrectionForm'
import { useVoucher, useAccounts } from '@/hooks/useVouchers'
import Link from 'next/link'
import { useState } from 'react'
import { api } from '@/lib/api'

export const dynamic = 'force-dynamic'

export default function VoucherDetailPage({ params }: { params: { id: string } }) {
  const { data: voucherData, isLoading, error } = useVoucher(params.id)
  const { data: accountsData } = useAccounts()
  const [isEditing, setIsEditing] = useState(false)
  const [teachAI, setTeachAI] = useState(true)
  const [correctionReason, setCorrectionReason] = useState('')
  const [editedRows, setEditedRows] = useState<any[]>([])

  const voucher = voucherData?.voucher

  if (isLoading) return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">Laddar verifikation...</div>
    </>
  )

  if (error || !voucher) return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8 text-red-600">Verifikation hittades inte</div>
    </>
  )

  const handleSaveCorrection = async () => {
    try {
      await api.recordCorrection(
        params.id,
        { rows: editedRows },
        correctionReason
      )
      alert('✅ Korrigering sparad! AI:n har lärt sig.')
      setIsEditing(false)
      window.location.reload()
    } catch (err) {
      alert('❌ Fel vid sparning av korrigering')
    }
  }

  return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Tillbaka-knapp */}
        <Link href="/vouchers" className="text-blue-600 hover:underline mb-4 inline-block">
          ← Tillbaka till lista
        </Link>

        <div className="bg-white rounded-lg shadow p-6">
          {/* Verifikationshuvud */}
          <div className="mb-6">
            <h2 className="text-2xl font-bold mb-2">Ver.nr {voucher.voucher_number}</h2>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-gray-600">Datum</span>
                <p className="font-semibold">{voucher.voucher_date}</p>
              </div>
              <div>
                <span className="text-gray-600">Status</span>
                <p className="font-semibold">
                  {voucher.status === 'posted' ? '✅ Bokförd' :
                   voucher.status === 'booked' ? '📊 Rapporterad' :
                   '📝 Utkast'}
                </p>
              </div>
              <div>
                <span className="text-gray-600">AI-genererad</span>
                <p className="font-semibold">{voucher.ai_generated ? '🤖 Ja' : 'Nej'}</p>
              </div>
            </div>
            <p className="mt-2 text-gray-700">{voucher.description}</p>
          </div>

          {/* Verifikationsrader */}
          <div className="mb-6">
            <h3 className="text-lg font-bold mb-3">Bokföringsrader</h3>
            <table className="w-full border-collapse border border-gray-300">
              <thead className="bg-gray-100">
                <tr>
                  <th className="border border-gray-300 px-4 py-2 text-left">Konto</th>
                  <th className="border border-gray-300 px-4 py-2 text-right">Debet</th>
                  <th className="border border-gray-300 px-4 py-2 text-right">Kredit</th>
                  <th className="border border-gray-300 px-4 py-2 text-left">Moms</th>
                </tr>
              </thead>
              <tbody>
                {(isEditing ? editedRows : voucher.rows).map((row: any, idx: number) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="border border-gray-300 px-4 py-2">
                      {isEditing ? (
                        <input
                          type="text"
                          value={row.account_code}
                          onChange={(e) => {
                            const newRows = [...editedRows]
                            newRows[idx].account_code = e.target.value
                            setEditedRows(newRows)
                          }}
                          className="w-full border px-2 py-1"
                        />
                      ) : (
                        `${row.account_code} ${row.account_name ? '- ' + row.account_name : ''}`
                      )}
                    </td>
                    <td className="border border-gray-300 px-4 py-2 text-right">
                      {row.debit?.toLocaleString('sv-SE') || '-'} kr
                    </td>
                    <td className="border border-gray-300 px-4 py-2 text-right">
                      {row.credit?.toLocaleString('sv-SE') || '-'} kr
                    </td>
                    <td className="border border-gray-300 px-4 py-2">
                      {row.vat_code || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Korrigeringsfunktionalitet */}
          {voucher.ai_generated && !isEditing && (
            <button
              onClick={() => {
                setIsEditing(true)
                setEditedRows(JSON.parse(JSON.stringify(voucher.rows)))
              }}
              className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 font-semibold"
            >
              ✏️ Korrigera
            </button>
          )}

          {/* Korrigeringsformulär - Extraherad komponent */}
          {isEditing && (
            <CorrectionForm
              voucherId={params.id}
              originalRows={voucher.rows}
              onSuccess={() => {
                setIsEditing(false)
                setTimeout(() => window.location.reload(), 500)
              }}
              onCancel={() => setIsEditing(false)}
            />
          )}

          {/* Ändringshistorik */}
          {voucher.audit_trail && voucher.audit_trail.length > 0 && (
            <div className="mt-6">
              <h3 className="text-lg font-bold mb-3">Ändringshistorik</h3>
              <div className="space-y-2">
                {voucher.audit_trail.map((entry: any, idx: number) => (
                  <div key={idx} className="bg-gray-50 border-l-4 border-gray-400 px-4 py-2 text-sm">
                    <strong>{entry.action}</strong> - {entry.created_by} ({entry.created_at})
                    {entry.details && <p className="text-gray-600">{entry.details}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
