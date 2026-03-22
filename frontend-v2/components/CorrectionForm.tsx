'use client'

import { useState } from 'react'
import { api } from '@/lib/api'

interface CorrectionFormProps {
  voucherId: string
  originalRows: any[]
  onSuccess: () => void
  onCancel: () => void
}

export function CorrectionForm({
  voucherId,
  originalRows,
  onSuccess,
  onCancel,
}: CorrectionFormProps) {
  const [editedRows, setEditedRows] = useState(originalRows)
  const [reason, setReason] = useState('')
  const [teachAI, setTeachAI] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  const handleAccountChange = (rowIndex: number, newAccount: string) => {
    const newRows = [...editedRows]
    newRows[rowIndex] = {
      ...newRows[rowIndex],
      account_code: newAccount,
    }
    setEditedRows(newRows)
  }

  const handleAmountChange = (rowIndex: number, newAmount: string) => {
    const newRows = [...editedRows]
    const amount = parseInt(newAmount) || 0
    if (editedRows[rowIndex].debit) {
      newRows[rowIndex].debit = amount
    } else {
      newRows[rowIndex].credit = amount
    }
    setEditedRows(newRows)
  }

  const handleSave = async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await api.recordCorrection(
        voucherId,
        { rows: editedRows },
        reason
      )

      if (teachAI && response.rule_id) {
        setSuccess(true)
        setTimeout(() => {
          onSuccess()
        }, 1500)
      } else {
        setSuccess(true)
        setTimeout(() => {
          onSuccess()
        }, 1500)
      }
    } catch (err: any) {
      setError(err.message || 'Fel vid sparning av korrigering')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 mt-6">
      <h3 className="text-lg font-bold mb-4">✏️ Korrigera verifikation</h3>

      {success && (
        <div className="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded mb-4">
          ✅ Korrigering sparad! {teachAI && '🤖 AI:n har lärt sig!'}
        </div>
      )}

      {error && (
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
          ❌ {error}
        </div>
      )}

      {/* Redigeringstabell */}
      <div className="mb-4 overflow-x-auto">
        <table className="w-full border-collapse border border-gray-300 text-sm">
          <thead className="bg-gray-100">
            <tr>
              <th className="border border-gray-300 px-2 py-2 text-left">Konto</th>
              <th className="border border-gray-300 px-2 py-2 text-right">Debet</th>
              <th className="border border-gray-300 px-2 py-2 text-right">Kredit</th>
              <th className="border border-gray-300 px-2 py-2 text-left">Moms</th>
            </tr>
          </thead>
          <tbody>
            {editedRows.map((row, idx) => (
              <tr key={idx} className="hover:bg-white">
                <td className="border border-gray-300 px-2 py-2">
                  <input
                    type="text"
                    value={row.account_code}
                    onChange={(e) => handleAccountChange(idx, e.target.value)}
                    className="w-full border border-gray-300 rounded px-2 py-1 text-sm"
                  />
                </td>
                <td className="border border-gray-300 px-2 py-2">
                  <input
                    type="number"
                    value={row.debit || ''}
                    onChange={(e) => handleAmountChange(idx, e.target.value)}
                    className="w-full border border-gray-300 rounded px-2 py-1 text-sm text-right"
                  />
                </td>
                <td className="border border-gray-300 px-2 py-2">
                  <input
                    type="number"
                    value={row.credit || ''}
                    onChange={(e) => handleAmountChange(idx, e.target.value)}
                    className="w-full border border-gray-300 rounded px-2 py-1 text-sm text-right"
                  />
                </td>
                <td className="border border-gray-300 px-2 py-2 text-sm">
                  {row.vat_code || '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Anledning till korrigering */}
      <div className="mb-4">
        <label className="block text-sm font-semibold mb-2">
          Anledning till korrigering (valfritt)
        </label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Förklara varför denna ändring behövdes..."
          className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
          rows={2}
        />
      </div>

      {/* AI-lärande checkbox */}
      <div className="mb-4 flex items-center gap-2">
        <input
          type="checkbox"
          id="teach-ai"
          checked={teachAI}
          onChange={(e) => setTeachAI(e.target.checked)}
          className="w-4 h-4 rounded"
        />
        <label htmlFor="teach-ai" className="text-sm font-semibold">
          🤖 Lär AI:n av denna korrigering (förbättrar framtida bokföringar)
        </label>
      </div>

      {/* Knappar */}
      <div className="flex gap-3">
        <button
          onClick={handleSave}
          disabled={isLoading}
          className="bg-green-600 text-white px-6 py-2 rounded hover:bg-green-700 disabled:opacity-50 font-semibold"
        >
          {isLoading ? 'Sparar...' : '✅ Spara korrigering'}
        </button>
        <button
          onClick={onCancel}
          disabled={isLoading}
          className="bg-gray-400 text-white px-6 py-2 rounded hover:bg-gray-500 disabled:opacity-50 font-semibold"
        >
          Avbryt
        </button>
      </div>
    </div>
  )
}
