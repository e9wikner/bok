'use client'

import { Header } from '@/components/Header'
import { useAccounts } from '@/hooks/useVouchers'

export const dynamic = 'force-dynamic'

export default function AccountsPage() {
  const { data, isLoading, error } = useAccounts()
  const accounts = data?.accounts || []

  if (isLoading) return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">Laddar kontoplan...</div>
    </>
  )

  if (error) return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8 text-red-600">Fel vid hämtning av konton</div>
    </>
  )

  const groupedAccounts = accounts.reduce((acc: any, account: any) => {
    const type = account.type || 'Övriga'
    if (!acc[type]) acc[type] = []
    acc[type].push(account)
    return acc
  }, {})

  return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-6">Kontoplan</h2>

        {Object.entries(groupedAccounts).map(([type, typeAccounts]: any) => (
          <div key={type} className="mb-8">
            <h3 className="text-xl font-bold mb-3 text-gray-700">{type}</h3>
            <table className="w-full border-collapse border border-gray-300">
              <thead className="bg-gray-100">
                <tr>
                  <th className="border border-gray-300 px-4 py-2 text-left">Kontonummer</th>
                  <th className="border border-gray-300 px-4 py-2 text-left">Kontonamn</th>
                  <th className="border border-gray-300 px-4 py-2 text-right">Saldo</th>
                </tr>
              </thead>
              <tbody>
                {typeAccounts.map((account: any) => (
                  <tr key={account.code} className="hover:bg-gray-50">
                    <td className="border border-gray-300 px-4 py-2 font-mono">{account.code}</td>
                    <td className="border border-gray-300 px-4 py-2">{account.name}</td>
                    <td className="border border-gray-300 px-4 py-2 text-right">
                      {account.balance?.toLocaleString('sv-SE') || '0'} kr
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
      </div>
    </>
  )
}
