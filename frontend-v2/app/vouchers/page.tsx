'use client'

import { Header } from '@/components/Header'
import { VoucherList } from '@/components/VoucherList'

export const dynamic = 'force-dynamic'

export default function VouchersPage() {
  return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-6">Verifikationer</h2>
        <VoucherList />
      </div>
    </>
  )
}
