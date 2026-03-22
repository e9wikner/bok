'use client'

import { Header } from '@/components/Header'
import { useVouchers, useAccounts, useLearningRules } from '@/hooks/useVouchers'

export default function DashboardPage() {
  const { data: vouchersData } = useVouchers()
  const { data: accountsData } = useAccounts()
  const { data: rulesData } = useLearningRules()

  const totalVouchers = vouchersData?.total || 0
  const aiGeneratedCount = vouchersData?.vouchers?.filter((v: any) => v.ai_generated).length || 0
  const learningRulesCount = rulesData?.rules?.length || 0

  return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-8">Översikt</h2>

        {/* KPI-kort */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-gray-600 text-sm font-semibold">Totala verifikationer</h3>
            <p className="text-3xl font-bold text-blue-600">{totalVouchers}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-gray-600 text-sm font-semibold">AI-bokförda</h3>
            <p className="text-3xl font-bold text-purple-600">{aiGeneratedCount}</p>
          </div>
          <div className="bg-white rounded-lg shadow p-6">
            <h3 className="text-gray-600 text-sm font-semibold">Inlärda regler</h3>
            <p className="text-3xl font-bold text-green-600">{learningRulesCount}</p>
          </div>
        </div>

        {/* Info */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <h3 className="text-lg font-bold mb-2">🚀 Välkommen till Bokföringssystem v2</h3>
          <p className="text-gray-700">
            Modern bokförings- och faktureringssystem byggt för AI-samarbete. 
            Förbätta dina bokföringsprocesser och låt AI:n lära sig från dina korrigeringar.
          </p>
        </div>
      </div>
    </>
  )
}
