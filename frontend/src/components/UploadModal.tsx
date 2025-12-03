import { useState, useRef, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, X, FileText, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { api } from '../api/client'

interface UploadModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function UploadModal({ isOpen, onClose }: UploadModalProps) {
  const [dragActive, setDragActive] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const uploadMutation = useMutation({
    mutationFn: (file: File) => api.uploadDocument(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      setTimeout(() => {
        setFile(null)
        onClose()
      }, 1500)
    },
  })

  // Reset mutation state when modal opens
  useEffect(() => {
    if (isOpen) {
      uploadMutation.reset()
      setFile(null)
    }
  }, [isOpen])

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files?.[0]) {
      setFile(e.dataTransfer.files[0])
    }
  }

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      setFile(e.target.files[0])
    }
  }

  const handleUpload = () => {
    if (file) {
      uploadMutation.mutate(file)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-surface-900 rounded-2xl border border-surface-700 shadow-2xl animate-slide-up">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-surface-800">
          <h2 className="text-lg font-semibold text-white">Upload Document</h2>
          <button
            onClick={onClose}
            className="p-1 rounded-lg text-surface-400 hover:text-white hover:bg-surface-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {uploadMutation.isSuccess ? (
            <div className="flex flex-col items-center py-8 animate-fade-in">
              <div className="w-16 h-16 rounded-full bg-vault-500/20 flex items-center justify-center mb-4">
                <CheckCircle className="w-8 h-8 text-vault-400" />
              </div>
              <h3 className="text-lg font-medium text-white mb-1">Upload Successful!</h3>
              <p className="text-surface-400 text-sm">Processing will begin shortly</p>
            </div>
          ) : uploadMutation.isError ? (
            <div className="flex flex-col items-center py-8 animate-fade-in">
              <div className="w-16 h-16 rounded-full bg-red-500/20 flex items-center justify-center mb-4">
                <AlertCircle className="w-8 h-8 text-red-400" />
              </div>
              <h3 className="text-lg font-medium text-white mb-1">Upload Failed</h3>
              <p className="text-red-400 text-sm">{(uploadMutation.error as Error).message}</p>
              <button
                onClick={() => uploadMutation.reset()}
                className="mt-4 text-vault-400 hover:text-vault-300 text-sm"
              >
                Try again
              </button>
            </div>
          ) : (
            <>
              {/* Dropzone */}
              <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => inputRef.current?.click()}
                className={`relative flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-xl cursor-pointer transition-all ${
                  dragActive
                    ? 'border-vault-500 bg-vault-500/10'
                    : 'border-surface-700 hover:border-surface-600 hover:bg-surface-800/50'
                }`}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".pdf,.docx,.txt"
                  onChange={handleChange}
                  className="hidden"
                />
                <Upload className={`w-10 h-10 mb-3 ${dragActive ? 'text-vault-400' : 'text-surface-500'}`} />
                <p className="text-sm text-surface-300 mb-1">
                  {dragActive ? 'Drop your file here' : 'Drag and drop or click to upload'}
                </p>
                <p className="text-xs text-surface-500">PDF, DOCX, or TXT up to 50MB</p>
              </div>

              {/* Selected file */}
              {file && (
                <div className="mt-4 p-3 bg-surface-800 rounded-lg flex items-center gap-3 animate-fade-in">
                  <div className="w-10 h-10 rounded-lg bg-surface-700 flex items-center justify-center">
                    <FileText className="w-5 h-5 text-surface-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-white truncate">{file.name}</p>
                    <p className="text-xs text-surface-500">
                      {(file.size / (1024 * 1024)).toFixed(2)} MB
                    </p>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setFile(null)
                    }}
                    className="p-1 rounded-lg text-surface-400 hover:text-white hover:bg-surface-700 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {!uploadMutation.isSuccess && !uploadMutation.isError && (
          <div className="flex justify-end gap-3 p-4 border-t border-surface-800">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-surface-300 hover:text-white hover:bg-surface-800 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleUpload}
              disabled={!file || uploadMutation.isPending}
              className="px-4 py-2 rounded-lg bg-vault-600 hover:bg-vault-500 text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {uploadMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Uploading...
                </>
              ) : (
                'Upload'
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

