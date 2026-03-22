'use client'

import { useState, useRef } from 'react'
import { api } from '@/lib/api'

interface FileUploadProps {
  onSuccess?: () => void
  acceptedTypes?: string[]
  maxSizeMB?: number
}

export function FileUpload({
  onSuccess,
  acceptedTypes = ['.sie4', '.txt', '.csv'],
  maxSizeMB = 10,
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [uploadedFile, setUploadedFile] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => {
    setIsDragging(false)
  }

  const validateFile = (file: File): boolean => {
    // Kontrollera filtyp
    const ext = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!acceptedTypes.includes(ext)) {
      setError(`Filtyp ${ext} stöds inte. Accepterade: ${acceptedTypes.join(', ')}`)
      return false
    }

    // Kontrollera filstorlek
    const sizeMB = file.size / (1024 * 1024)
    if (sizeMB > maxSizeMB) {
      setError(`Filen är för stor (${sizeMB.toFixed(1)}MB > ${maxSizeMB}MB)`)
      return false
    }

    return true
  }

  const handleFile = async (file: File) => {
    setError(null)
    setSuccess(false)

    if (!validateFile(file)) return

    setIsUploading(true)
    setUploadedFile(file.name)

    try {
      const formData = new FormData()
      formData.append('file', file)

      // Bestäm endpoint baserat på filtyp
      const endpoint = file.name.endsWith('.sie4')
        ? '/api/v1/import/sie4'
        : '/api/v1/import/csv'

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer dev-key-change-in-production',
        },
        body: formData,
      })

      if (response.ok) {
        const result = await response.json()
        setSuccess(true)
        setUploadedFile(null)
        setTimeout(() => {
          onSuccess?.()
        }, 2000)
      } else {
        const errorData = await response.json()
        setError(errorData.detail || 'Fel vid uppladdning av fil')
        setUploadedFile(null)
      }
    } catch (err: any) {
      setError(err.message || 'Fel vid uppladdning')
      setUploadedFile(null)
    } finally {
      setIsUploading(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)

    const files = e.dataTransfer.files
    if (files.length > 0) {
      handleFile(files[0])
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files
    if (files?.length) {
      handleFile(files[0])
    }
  }

  return (
    <div className="w-full">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition ${
          isDragging
            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900'
            : 'border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleInputChange}
          accept={acceptedTypes.join(',')}
          className="hidden"
        />

        {isUploading ? (
          <div>
            <p className="text-lg font-semibold mb-2">📤 Laddar upp: {uploadedFile}</p>
            <div className="w-full bg-gray-300 dark:bg-gray-600 rounded-full h-2">
              <div className="bg-blue-600 h-2 rounded-full animate-pulse"></div>
            </div>
          </div>
        ) : success ? (
          <div>
            <p className="text-2xl mb-2">✅</p>
            <p className="text-lg font-semibold text-green-600 dark:text-green-400">
              Fil importerad framgångsrikt!
            </p>
          </div>
        ) : (
          <div>
            <p className="text-3xl mb-2">📁</p>
            <p className="text-lg font-semibold mb-1">
              Dra och släpp fil här
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              eller klicka för att välja
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-500 mt-2">
              Accepterade: {acceptedTypes.join(', ')} (max {maxSizeMB}MB)
            </p>
          </div>
        )}
      </div>

      {error && (
        <div className="mt-4 bg-red-100 dark:bg-red-900 border border-red-400 dark:border-red-600 text-red-700 dark:text-red-100 px-4 py-3 rounded">
          ❌ {error}
        </div>
      )}
    </div>
  )
}
