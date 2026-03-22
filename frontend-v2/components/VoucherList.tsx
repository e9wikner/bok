'use client'

import Link from 'next/link'
import { useVouchers } from '@/hooks/useVouchers'
import { useState } from 'react'

export function VoucherList() {
  const [offset, setOffset] = useState(0)
  const limit = 15

  const { data, isLoading, error } = useVouchers(undefined, limit, offset)
  const vouchers = data?.vouchers || []
  const total = data?.total || 0

  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(offset / limit) + 1

  if (isLoading) return <div className="p-4">Laddar verifikationer...</div>
  if (error) return <div className="p-4 text-red-600">Fel vid hämtning av verifikationer</div>

  return (
    <div className="space-y-4">
      <table className="w-full border-collapse border border-gray-300">
        <thead className="bg-gray-100">
          <tr>
            <th className="border border-gray-300 px-4 py-2 text-left">Ver.nr</th>
            <th className="border border-gray-300 px-4 py-2 text-left">Datum</th>
            <th className="border border-gray-300 px-4 py-2 text-left">Beskrivning</th>
            <th className="border border-gray-300 px-4 py-2 text-right">Belopp</th>
            <th className="border border-gray-300 px-4 py-2 text-left">Status</th>
            <th className="border border-gray-300 px-4 py-2 text-center">Åtgärd</th>
          </tr>
        </thead>
        <tbody>
          {vouchers.map((voucher: any) => (
            <tr key={voucher.id} className="hover:bg-gray-50 cursor-pointer">
              <td className="border border-gray-300 px-4 py-2">{voucher.voucher_number}</td>
              <td className="border border-gray-300 px-4 py-2">{voucher.voucher_date}</td>
              <td className="border border-gray-300 px-4 py-2">{voucher.description}</td>
              <td className="border border-gray-300 px-4 py-2 text-right">
                {voucher.rows.reduce((sum: number, row: any) => sum + (row.debit || 0), 0).toLocaleString('sv-SE')} kr
              </td>
              <td className="border border-gray-300 px-4 py-2">
                <span className={`px-2 py-1 rounded text-sm ${
                  voucher.status === 'posted' ? 'bg-green-100 text-green-700' :
                  voucher.status === 'booked' ? 'bg-blue-100 text-blue-700' :
                  'bg-yellow-100 text-yellow-700'
                }`}>
                  {voucher.status === 'posted' ? '✅ Bokförd' :
                   voucher.status === 'booked' ? '📊 Rapporterad' :
                   '📝 Utkast'}
                </span>
              </td>
              <td className="border border-gray-300 px-4 py-2 text-center">
                <Link href={`/vouchers/${voucher.id}`} className="text-blue-600 hover:underline">
                  Visa
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Paginering */}
      <div className="flex justify-between items-center py-4">
        <span className="text-gray-600">
          Visar {offset + 1}-{Math.min(offset + limit, total)} av {total} verifikationer
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setOffset(Math.max(0, offset - limit))}
            disabled={offset === 0}
            className="px-4 py-2 bg-gray-200 rounded disabled:opacity-50"
          >
            ← Föregående
          </button>
          <span className="px-4 py-2">Sida {currentPage} av {totalPages}</span>
          <button
            onClick={() => setOffset(offset + limit)}
            disabled={offset + limit >= total}
            className="px-4 py-2 bg-gray-200 rounded disabled:opacity-50"
          >
            Nästa →
          </button>
        </div>
      </div>
    </div>
  )
}
