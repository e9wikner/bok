import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Bokföringssystem',
  description: 'Modern bokföringssystem för svenska företag',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="sv">
      <body className="bg-gray-50">{children}</body>
    </html>
  )
}
