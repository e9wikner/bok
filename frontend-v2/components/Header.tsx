'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useDarkMode } from '@/hooks/useDarkMode'

export function Header() {
  const pathname = usePathname()
  const { isDark, toggle, isMounted } = useDarkMode()

  const isActive = (path: string) => 
    pathname === path 
      ? 'text-blue-600 dark:text-blue-400' 
      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'

  if (!isMounted) return null

  return (
    <header className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
      <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">📊 Bokföringssystem</h1>
        <nav className="flex gap-6 items-center">
          <Link href="/" className={isActive('/')}>Översikt</Link>
          <Link href="/vouchers" className={isActive('/vouchers')}>Verifikationer</Link>
          <Link href="/accounts" className={isActive('/accounts')}>Konton</Link>
          <Link href="/reports" className={isActive('/reports')}>Rapporter</Link>
          <Link href="/learning" className={isActive('/learning')}>AI-lärande</Link>
          <Link href="/settings" className={isActive('/settings')}>⚙️</Link>
          
          {/* Dark mode toggle */}
          <button
            onClick={toggle}
            className="ml-4 px-3 py-1 rounded bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white hover:bg-gray-300 dark:hover:bg-gray-600"
            aria-label="Toggle dark mode"
          >
            {isDark ? '☀️' : '🌙'}
          </button>
        </nav>
      </div>
    </header>
  )
}
