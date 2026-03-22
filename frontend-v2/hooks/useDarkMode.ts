'use client'

import { useEffect, useState } from 'react'

export function useDarkMode() {
  const [isDark, setIsDark] = useState(false)
  const [isMounted, setIsMounted] = useState(false)

  useEffect(() => {
    setIsMounted(true)
    
    // Hämta från localStorage eller system preference
    const saved = localStorage.getItem('darkMode')
    if (saved !== null) {
      setIsDark(saved === 'true')
    } else {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      setIsDark(prefersDark)
    }
  }, [])

  useEffect(() => {
    if (!isMounted) return

    const root = document.documentElement
    if (isDark) {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
    localStorage.setItem('darkMode', isDark.toString())
  }, [isDark, isMounted])

  const toggle = () => setIsDark(!isDark)

  return { isDark, toggle, isMounted }
}
