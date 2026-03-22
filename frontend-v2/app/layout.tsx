import type { Metadata } from 'next'
import './globals.css'
import { Providers } from './providers'

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
      <body className="bg-gray-50">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
