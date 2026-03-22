'use client'

import { Header } from '@/components/Header'
import { FileUpload } from '@/components/FileUpload'
import { useState } from 'react'

export default function SettingsPage() {
  const [importSuccess, setImportSuccess] = useState(false)

  return (
    <>
      <Header />
      <div className="max-w-7xl mx-auto px-4 py-8">
        <h2 className="text-3xl font-bold mb-8">⚙️ Inställningar</h2>

        {/* Import-sektion */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-8 mb-8">
          <h3 className="text-2xl font-bold mb-2">📥 Importera data</h3>
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            Importera bokföringsdata från SIE4-filer eller CSV
          </p>

          <div className="mb-8">
            <h4 className="text-lg font-semibold mb-4">SIE4-fil</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              Importera komplett bokföringsdata från SIE4-format (Standard för Svenska bokföringsdata)
            </p>
            <FileUpload
              acceptedTypes={['.sie4', '.txt']}
              maxSizeMB={20}
              onSuccess={() => {
                setImportSuccess(true)
                setTimeout(() => setImportSuccess(false), 3000)
              }}
            />
          </div>

          <hr className="my-8 dark:border-gray-700" />

          <div>
            <h4 className="text-lg font-semibold mb-4">Bankexport (CSV)</h4>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              Importera banktransaktioner för auto-kategorisering
            </p>
            <FileUpload
              acceptedTypes={['.csv']}
              maxSizeMB={10}
              onSuccess={() => {
                setImportSuccess(true)
                setTimeout(() => setImportSuccess(false), 3000)
              }}
            />
          </div>
        </div>

        {/* API-information */}
        <div className="bg-blue-50 dark:bg-blue-900 border border-blue-200 dark:border-blue-800 rounded-lg p-8">
          <h3 className="text-lg font-bold mb-4 text-blue-900 dark:text-blue-100">🔌 API Information</h3>
          
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div>
              <p className="text-sm text-blue-700 dark:text-blue-300">API URL</p>
              <p className="font-mono text-sm bg-white dark:bg-gray-800 p-2 rounded">
                {process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}
              </p>
            </div>
            <div>
              <p className="text-sm text-blue-700 dark:text-blue-300">Frontend Version</p>
              <p className="font-mono text-sm bg-white dark:bg-gray-800 p-2 rounded">
                v2.0.0
              </p>
            </div>
          </div>

          <p className="text-sm text-blue-700 dark:text-blue-300">
            Dokumentation: <a href="https://api.bokfoering.local/docs" className="underline hover:no-underline">OpenAPI Docs</a>
          </p>
        </div>

        {/* Success message */}
        {importSuccess && (
          <div className="fixed bottom-4 right-4 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg">
            ✅ Fil importerad framgångsrikt!
          </div>
        )}
      </div>
    </>
  )
}
