import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, MessageSquarePlus, FileText, Sparkles, Search } from 'lucide-react'
import { api } from '../api/client'
import DocumentCard from '../components/DocumentCard'
import UploadModal from '../components/UploadModal'

export default function HomePage() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [uploadOpen, setUploadOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Fetch documents with polling for status updates
  const { data, isLoading } = useQuery({
    queryKey: ['documents'],
    queryFn: () => api.getDocuments(1, 100),
    refetchInterval: (query) => {
      // Poll more frequently if there are pending/processing documents
      const docs = query.state.data?.documents ?? []
      const hasPending = docs.some((d) => d.status === 'pending' || d.status === 'processing')
      return hasPending ? 3000 : 30000
    },
  })

  // Create chat mutation
  const createChatMutation = useMutation({
    mutationFn: (documentIds: string[]) => api.createChat(documentIds),
    onSuccess: (chat) => {
      queryClient.invalidateQueries({ queryKey: ['chats'] })
      navigate(`/chat/${chat.id}`)
    },
  })

  const toggleDocument = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleStartChat = () => {
    if (selectedIds.size > 0) {
      createChatMutation.mutate(Array.from(selectedIds))
    }
  }

  // Filter documents based on search
  const filteredDocuments = useMemo(() => {
    if (!data?.documents) return []
    if (!searchQuery.trim()) return data.documents
    const query = searchQuery.toLowerCase()
    return data.documents.filter((doc) =>
      doc.original_filename.toLowerCase().includes(query)
    )
  }, [data?.documents, searchQuery])

  // Stats
  const stats = useMemo(() => {
    if (!data?.documents) return { total: 0, completed: 0, processing: 0 }
    return {
      total: data.documents.length,
      completed: data.documents.filter((d) => d.status === 'completed').length,
      processing: data.documents.filter((d) => d.status === 'pending' || d.status === 'processing').length,
    }
  }, [data?.documents])

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <header className="flex-shrink-0 p-6 border-b border-surface-800">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-white flex items-center gap-2">
              <Sparkles className="w-6 h-6 text-vault-400" />
              Documents
            </h1>
            <p className="text-surface-400 mt-1">
              Select documents to start a conversation
            </p>
          </div>
          <button
            onClick={() => setUploadOpen(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-surface-800 hover:bg-surface-700 text-white font-medium transition-colors border border-surface-700"
          >
            <Plus className="w-4 h-4" />
            Upload
          </button>
        </div>

        {/* Stats bar */}
        <div className="flex items-center gap-6 mt-4 text-sm">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-surface-500" />
            <span className="text-surface-400">{stats.total} documents</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-vault-500" />
            <span className="text-surface-400">{stats.completed} ready</span>
          </div>
          {stats.processing > 0 && (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
              <span className="text-surface-400">{stats.processing} processing</span>
            </div>
          )}
        </div>

        {/* Search */}
        <div className="relative mt-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-500" />
          <input
            type="text"
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 rounded-lg bg-surface-800 border border-surface-700 text-white placeholder-surface-500 focus:border-vault-500 focus:ring-1 focus:ring-vault-500 transition-colors"
          />
        </div>
      </header>

      {/* Document Grid */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {[...Array(8)].map((_, i) => (
              <div
                key={i}
                className="h-40 rounded-xl bg-surface-800 animate-pulse"
              />
            ))}
          </div>
        ) : filteredDocuments.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-20 h-20 rounded-2xl bg-surface-800 flex items-center justify-center mb-4">
              <FileText className="w-10 h-10 text-surface-600" />
            </div>
            <h3 className="text-lg font-medium text-white mb-1">
              {searchQuery ? 'No documents found' : 'No documents yet'}
            </h3>
            <p className="text-surface-500 mb-4">
              {searchQuery
                ? 'Try a different search term'
                : 'Upload your first document to get started'}
            </p>
            {!searchQuery && (
              <button
                onClick={() => setUploadOpen(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-vault-600 hover:bg-vault-500 text-white font-medium transition-colors"
              >
                <Plus className="w-4 h-4" />
                Upload Document
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {filteredDocuments.map((doc, index) => (
              <div
                key={doc.id}
                className="animate-fade-in"
                style={{ animationDelay: `${index * 50}ms` }}
              >
                <DocumentCard
                  document={doc}
                  selected={selectedIds.has(doc.id)}
                  onToggle={() => toggleDocument(doc.id)}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Start Chat Bar */}
      {selectedIds.size > 0 && (
        <div className="flex-shrink-0 p-4 border-t border-surface-800 bg-surface-900/80 backdrop-blur-sm animate-slide-up">
          <div className="flex items-center justify-between gap-4">
            <div className="text-sm text-surface-400">
              <span className="text-white font-medium">{selectedIds.size}</span>{' '}
              document{selectedIds.size !== 1 ? 's' : ''} selected
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSelectedIds(new Set())}
                className="px-4 py-2 rounded-lg text-surface-400 hover:text-white hover:bg-surface-800 transition-colors"
              >
                Clear selection
              </button>
              <button
                onClick={handleStartChat}
                disabled={createChatMutation.isPending}
                className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-vault-600 hover:bg-vault-500 text-white font-medium transition-colors shadow-lg shadow-vault-600/20 disabled:opacity-50"
              >
                <MessageSquarePlus className="w-4 h-4" />
                {createChatMutation.isPending ? 'Creating...' : 'Start Chat'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Upload Modal */}
      <UploadModal isOpen={uploadOpen} onClose={() => setUploadOpen(false)} />
    </div>
  )
}

