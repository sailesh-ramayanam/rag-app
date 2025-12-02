import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Send,
  FileText,
  Loader2,
  User,
  Sparkles,
  Download,
  Trash2,
  AlertCircle,
} from 'lucide-react'
import { api } from '../api/client'
import type { Source, QueryType, RetrievalStrategy } from '../types'

function formatTime(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

interface SourcesPanelProps {
  sources: Source[]
  queryInfo?: { type: QueryType; strategy: RetrievalStrategy } | null
}

const strategyLabels: Record<RetrievalStrategy, string> = {
  document_summaries: 'Document Summary',
  conversation_history: 'Conversation Context',
  vector_search: 'Document Search',
  mixed: 'Mixed Retrieval',
}

const strategyColors: Record<RetrievalStrategy, string> = {
  document_summaries: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  conversation_history: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  vector_search: 'bg-vault-500/20 text-vault-400 border-vault-500/30',
  mixed: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
}

function SourcesPanel({ sources, queryInfo }: SourcesPanelProps) {
  if (sources.length === 0 && !queryInfo) return null

  return (
    <div className="mt-3 p-3 bg-surface-800/50 rounded-lg border border-surface-700">
      {queryInfo && (
        <div className="flex items-center gap-2 mb-2">
          <span className={`px-2 py-0.5 rounded-full text-xs border ${strategyColors[queryInfo.strategy]}`}>
            {strategyLabels[queryInfo.strategy]}
          </span>
        </div>
      )}
      {sources.length > 0 && (
        <>
          <h4 className="text-xs font-medium text-surface-400 mb-2">Sources</h4>
          <div className="space-y-2">
            {sources.map((source, i) => (
              <div
                key={i}
                className="p-2 bg-surface-900 rounded-md border border-surface-700 text-xs"
              >
                <div className="flex items-center gap-2 mb-1">
                  <FileText className="w-3 h-3 text-vault-400" />
                  <span className="text-vault-400 font-medium truncate">
                    {source.document_name}
                  </span>
                  {source.page_number && (
                    <span className="text-surface-500">• Page {source.page_number}</span>
                  )}
                  <span className="text-surface-600 ml-auto">
                    {(source.similarity * 100).toFixed(0)}% match
                  </span>
                </div>
                <p className="text-surface-400 line-clamp-2">{source.chunk_content}</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default function ChatPage() {
  const { chatId } = useParams<{ chatId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [message, setMessage] = useState('')
  const [lastSources, setLastSources] = useState<Source[]>([])
  const [lastQueryInfo, setLastQueryInfo] = useState<{ type: QueryType; strategy: RetrievalStrategy } | null>(null)
  const [pendingMessage, setPendingMessage] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Fetch chat details
  const { data: chat, isLoading, error } = useQuery({
    queryKey: ['chat', chatId],
    queryFn: () => api.getChat(chatId!),
    enabled: !!chatId,
  })

  // Reset state when switching chats
  useEffect(() => {
    setLastSources([])
    setLastQueryInfo(null)
    setPendingMessage(null)
  }, [chatId])

  // Send message mutation
  const sendMutation = useMutation({
    mutationFn: ({ question }: { question: string }) =>
      api.sendMessage(chatId!, question),
    onSuccess: (response) => {
      setLastSources(response.sources)
      setLastQueryInfo({ type: response.query_type, strategy: response.retrieval_strategy })
      setPendingMessage(null)
      queryClient.invalidateQueries({ queryKey: ['chat', chatId] })
      queryClient.invalidateQueries({ queryKey: ['chats'] })
    },
    onError: () => {
      setPendingMessage(null)
    },
  })

  // Delete chat mutation
  const deleteMutation = useMutation({
    mutationFn: () => api.deleteChat(chatId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats'] })
      navigate('/')
    },
  })

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chat?.messages, sendMutation.isPending])

  // Handle send
  const handleSend = () => {
    const trimmed = message.trim()
    if (trimmed && !sendMutation.isPending) {
      setMessage('')
      setLastSources([])
      setLastQueryInfo(null)
      setPendingMessage(trimmed)
      sendMutation.mutate({ question: trimmed })
    }
  }

  // Handle keyboard
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-vault-400 animate-spin" />
      </div>
    )
  }

  if (error || !chat) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-6">
        <AlertCircle className="w-12 h-12 text-red-400 mb-4" />
        <h2 className="text-xl font-semibold text-white mb-2">Chat not found</h2>
        <p className="text-surface-400 mb-4">
          This chat may have been deleted or doesn't exist.
        </p>
        <button
          onClick={() => navigate('/')}
          className="px-4 py-2 rounded-lg bg-vault-600 hover:bg-vault-500 text-white font-medium transition-colors"
        >
          Go Home
        </button>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header with document links */}
      <header className="flex-shrink-0 p-4 border-b border-surface-800 bg-surface-900/50">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold text-white truncate">
              {chat.title || 'New Chat'}
            </h1>
            <div className="flex flex-wrap items-center gap-2 mt-2">
              {chat.documents.map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => api.downloadDocument(doc.id, doc.original_filename)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-surface-800 border border-surface-700 text-xs hover:bg-surface-700 hover:border-surface-600 transition-colors"
                  title={`Download ${doc.original_filename}`}
                >
                  <FileText className="w-3 h-3 text-vault-400" />
                  <span className="text-surface-300 truncate max-w-[150px]">
                    {doc.original_filename}
                  </span>
                  <Download className="w-3 h-3 text-surface-500" />
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={() => {
              if (confirm('Delete this chat?')) {
                deleteMutation.mutate()
              }
            }}
            className="p-2 rounded-lg text-surface-500 hover:text-red-400 hover:bg-red-400/10 transition-colors"
            title="Delete chat"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chat.messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-vault-500/20 to-vault-600/20 flex items-center justify-center mb-4">
              <Sparkles className="w-8 h-8 text-vault-400" />
            </div>
            <h3 className="text-lg font-medium text-white mb-1">
              Start the conversation
            </h3>
            <p className="text-surface-500 max-w-sm">
              Ask questions about your documents. I'll find relevant information and provide
              answers with source citations.
            </p>
          </div>
        ) : (
          <>
            {chat.messages.map((msg, index) => (
              <div
                key={msg.id}
                className={`flex gap-3 animate-fade-in ${
                  msg.role === 'user' ? 'flex-row-reverse' : ''
                }`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {/* Avatar */}
                <div
                  className={`w-8 h-8 rounded-lg flex-shrink-0 flex items-center justify-center ${
                    msg.role === 'user'
                      ? 'bg-surface-700'
                      : 'bg-gradient-to-br from-vault-500 to-vault-600'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <User className="w-4 h-4 text-surface-300" />
                  ) : (
                    <Sparkles className="w-4 h-4 text-white" />
                  )}
                </div>

                {/* Message bubble */}
                <div
                  className={`flex-1 max-w-[80%] ${
                    msg.role === 'user' ? 'text-right' : ''
                  }`}
                >
                  <div
                    className={`inline-block p-4 rounded-2xl ${
                      msg.role === 'user'
                        ? 'bg-vault-600 text-white rounded-tr-sm'
                        : 'bg-surface-800 text-surface-200 rounded-tl-sm'
                    }`}
                  >
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {msg.content}
                    </p>
                  </div>
                  <p className="text-xs text-surface-600 mt-1">
                    {formatTime(msg.created_at)}
                  </p>

                  {/* Show sources for the last assistant message */}
                  {msg.role === 'assistant' &&
                    index === chat.messages.length - 1 &&
                    (lastSources.length > 0 || lastQueryInfo) && (
                      <SourcesPanel sources={lastSources} queryInfo={lastQueryInfo} />
                    )}
                </div>
              </div>
            ))}

            {/* Pending user message (optimistic UI) */}
            {pendingMessage && (
              <div className="flex gap-3 animate-fade-in flex-row-reverse">
                <div className="w-8 h-8 rounded-lg flex-shrink-0 flex items-center justify-center bg-surface-700">
                  <User className="w-4 h-4 text-surface-300" />
                </div>
                <div className="flex-1 max-w-[80%] text-right">
                  <div className="inline-block p-4 rounded-2xl bg-vault-600 text-white rounded-tr-sm">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">
                      {pendingMessage}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Typing indicator */}
            {sendMutation.isPending && (
              <div className="flex gap-3 animate-fade-in">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-vault-500 to-vault-600 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
                <div className="bg-surface-800 rounded-2xl rounded-tl-sm p-4">
                  <div className="flex items-center gap-1">
                    <div className="w-2 h-2 bg-surface-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 bg-surface-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 bg-surface-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="flex-shrink-0 p-4 border-t border-surface-800 bg-surface-900/50">
        <div className="flex gap-3">
          <textarea
            ref={inputRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents..."
            rows={1}
            className="flex-1 resize-none px-4 py-3 rounded-xl bg-surface-800 border border-surface-700 text-white placeholder-surface-500 focus:border-vault-500 focus:ring-1 focus:ring-vault-500 transition-colors"
            style={{ minHeight: '48px', maxHeight: '120px' }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement
              target.style.height = 'auto'
              target.style.height = `${Math.min(target.scrollHeight, 120)}px`
            }}
          />
          <button
            onClick={handleSend}
            disabled={!message.trim() || sendMutation.isPending}
            className="w-12 h-12 rounded-xl bg-vault-600 hover:bg-vault-500 text-white flex items-center justify-center transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-vault-600/20"
          >
            {sendMutation.isPending ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>

        {sendMutation.isError && (
          <div className="mt-2 p-2 rounded-lg bg-red-400/10 border border-red-400/20 text-red-400 text-sm flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {(sendMutation.error as Error).message}
          </div>
        )}
      </div>
    </div>
  )
}

