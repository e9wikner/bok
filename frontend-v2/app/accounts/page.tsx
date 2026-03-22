'use client'

import { Header } from '@/components/Header'
import { useAccounts } from '@/hooks/useVouchers'

export default function AccountsPage() {
  const { data, isLoading, error } = useAccounts()
  const accounts = data?.accounts || []

  if (isLoading) return <div className="p-4">Laddar kontoplan...</div>
  if (error) return <div className="p-4 text-red-600">Fel vid hämtning av kontoplan</div>

  return (
    <>
      <Header />
      <div className="max-w-6xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-6">Kontoplan</h2>

        <table className="w-full border-collapse border border-gray-300">
          <thead className="bg-gray-100">
            <tr>
              <th className="border border-gray-300 px-4 py-2 text-left">Kontonummer</th>
              <th className="border border-gray-300 px-4 py-2 text-left">Kontonamn</th>
              <th className="border border-gray-300 px-4 py-2 text-left">Typ</th>
              <th className="border border-gray-300 px-4 py-2 text-right">Saldo</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((account: any) => (
              <tr key={account.code} className="hover:bg-gray-50">
                <td className="border border-gray-300 px-4 py-2 font-mono font-bold">{account.code}</td>
                <td className="border border-gray-300 px-4 py-2">{account.name}</td>
                <td className="border border-gray-300 px-4 py-2">{account.type}</td>
                <td className="border border-gray-300 px-4 py-2 text-right">
                  {account.balance ? account.balance.toLocaleString('sv-SE') : '0'} kr
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
