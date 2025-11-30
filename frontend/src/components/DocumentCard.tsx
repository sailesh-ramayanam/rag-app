import { FileText, FileCheck, Clock, AlertCircle, Loader2 } from 'lucide-react'
import type { Document, ProcessingStatus } from '../types'

interface DocumentCardProps {
  document: Document
  selected: boolean
  onToggle: () => void
}

const statusConfig: Record<
  ProcessingStatus,
  { icon: typeof FileText; color: string; bg: string; label: string }
> = {
  pending: {
    icon: Clock,
    color: 'text-amber-400',
    bg: 'bg-amber-400/10',
    label: 'Pending',
  },
  processing: {
    icon: Loader2,
    color: 'text-blue-400',
    bg: 'bg-blue-400/10',
    label: 'Processing',
  },
  completed: {
    icon: FileCheck,
    color: 'text-vault-400',
    bg: 'bg-vault-400/10',
    label: 'Ready',
  },
  failed: {
    icon: AlertCircle,
    color: 'text-red-400',
    bg: 'bg-red-400/10',
    label: 'Failed',
  },
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function DocumentCard({ document, selected, onToggle }: DocumentCardProps) {
  const status = statusConfig[document.status]
  const StatusIcon = status.icon
  const isSelectable = document.status === 'completed'

  return (
    <div
      onClick={() => isSelectable && onToggle()}
      className={`doc-card relative p-4 rounded-xl border transition-all ${
        selected
          ? 'border-vault-500 bg-vault-500/10 ring-1 ring-vault-500/30'
          : isSelectable
          ? 'border-surface-700 bg-surface-800/50 hover:border-surface-600 cursor-pointer'
          : 'border-surface-800 bg-surface-900/50 opacity-60 cursor-not-allowed'
      }`}
    >
      {/* Selection indicator */}
      {isSelectable && (
        <div
          className={`absolute top-3 right-3 w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${
            selected
              ? 'border-vault-500 bg-vault-500'
              : 'border-surface-600 bg-transparent'
          }`}
        >
          {selected && (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          )}
        </div>
      )}

      {/* Document icon */}
      <div className="w-10 h-10 rounded-lg bg-surface-700/50 flex items-center justify-center mb-3">
        <FileText className="w-5 h-5 text-surface-400" />
      </div>

      {/* Document name */}
      <h3 className="font-medium text-white text-sm mb-1 truncate pr-6" title={document.original_filename}>
        {document.original_filename}
      </h3>

      {/* Meta info */}
      <div className="flex items-center gap-3 text-xs text-surface-500 mb-3">
        <span>{formatFileSize(document.file_size)}</span>
        {document.page_count && <span>{document.page_count} pages</span>}
        {document.chunk_count > 0 && <span>{document.chunk_count} chunks</span>}
      </div>

      {/* Status badge */}
      <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium ${status.bg} ${status.color}`}>
        <StatusIcon className={`w-3 h-3 ${document.status === 'processing' ? 'animate-spin' : ''}`} />
        <span>{status.label}</span>
      </div>

      {/* Date */}
      <p className="text-xs text-surface-600 mt-2">{formatDate(document.created_at)}</p>
    </div>
  )
}

