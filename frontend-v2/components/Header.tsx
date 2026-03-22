'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

export function Header() {
  const pathname = usePathname()

  const isActive = (path: string) => pathname === path ? 'text-blue-600' : 'text-gray-600 hover:text-gray-900'

  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900">📊 Bokföringssystem</h1>
        <nav className="flex gap-6">
          <Link href="/" className={isActive('/')}>Översikt</Link>
          <Link href="/vouchers" className={isActive('/vouchers')}>Verifikationer</Link>
          <Link href="/accounts" className={isActive('/accounts')}>Konton</Link>
          <Link href="/reports" className={isActive('/reports')}>Rapporter</Link>
          <Link href="/learning" className={isActive('/learning')}>AI-lärande</Link>
        </nav>
      </div>
    </header>
  )
}
