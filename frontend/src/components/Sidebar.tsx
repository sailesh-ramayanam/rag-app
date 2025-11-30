import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  MessageSquare,
  Settings,
  ChevronDown,
  ChevronRight,
  Plus,
  FileText,
  BarChart3,
  Sparkles,
} from 'lucide-react'
import { api } from '../api/client'

export default function Sidebar() {
  const [chatsOpen, setChatsOpen] = useState(true)
  const [adminOpen, setAdminOpen] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

  const { data: chatsData } = useQuery({
    queryKey: ['chats'],
    queryFn: () => api.getChats(),
    refetchInterval: 10000,
  })

  const isActive = (path: string) => location.pathname === path

  return (
    <aside className="w-64 h-full flex flex-col bg-surface-900 border-r border-surface-800">
      {/* Logo */}
      <div className="p-4 border-b border-surface-800">
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-vault-500 to-vault-600 flex items-center justify-center shadow-lg shadow-vault-500/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-semibold text-lg text-white group-hover:text-vault-400 transition-colors">
              Vault
            </h1>
            <p className="text-xs text-surface-500">Document AI</p>
          </div>
        </Link>
      </div>

      {/* New Chat Button */}
      <div className="p-3">
        <button
          onClick={() => navigate('/')}
          className="w-full flex items-center gap-2 px-4 py-2.5 rounded-lg bg-vault-600 hover:bg-vault-500 text-white font-medium transition-all shadow-lg shadow-vault-600/20 hover:shadow-vault-500/30"
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
      </div>

      {/* Navigation Sections */}
      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {/* Chats Section */}
        <div className="mb-4">
          <button
            onClick={() => setChatsOpen(!chatsOpen)}
            className="w-full flex items-center gap-2 px-2 py-2 text-sm font-medium text-surface-400 hover:text-white transition-colors"
          >
            {chatsOpen ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
            <MessageSquare className="w-4 h-4" />
            <span>Chats</span>
            {chatsData && (
              <span className="ml-auto text-xs bg-surface-800 px-2 py-0.5 rounded-full">
                {chatsData.total}
              </span>
            )}
          </button>

          {chatsOpen && (
            <div className="mt-1 ml-4 space-y-0.5 max-h-[40vh] overflow-y-auto">
              {chatsData?.chats.map((chat, index) => (
                <Link
                  key={chat.id}
                  to={`/chat/${chat.id}`}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all animate-fade-in ${
                    isActive(`/chat/${chat.id}`)
                      ? 'bg-vault-600/20 text-vault-400 border border-vault-600/30'
                      : 'text-surface-400 hover:text-white hover:bg-surface-800'
                  }`}
                  style={{ animationDelay: `${index * 30}ms` }}
                >
                  <FileText className="w-4 h-4 flex-shrink-0" />
                  <span className="truncate">
                    {chat.title || `Chat ${chat.id.slice(0, 8)}...`}
                  </span>
                </Link>
              ))}
              {chatsData?.chats.length === 0 && (
                <p className="px-3 py-2 text-sm text-surface-500 italic">
                  No chats yet
                </p>
              )}
            </div>
          )}
        </div>

        {/* Admin Section */}
        <div>
          <button
            onClick={() => setAdminOpen(!adminOpen)}
            className="w-full flex items-center gap-2 px-2 py-2 text-sm font-medium text-surface-400 hover:text-white transition-colors"
          >
            {adminOpen ? (
              <ChevronDown className="w-4 h-4" />
            ) : (
              <ChevronRight className="w-4 h-4" />
            )}
            <Settings className="w-4 h-4" />
            <span>Admin</span>
          </button>

          {adminOpen && (
            <div className="mt-1 ml-4 space-y-0.5">
              <Link
                to="/admin"
                className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all ${
                  isActive('/admin')
                    ? 'bg-vault-600/20 text-vault-400 border border-vault-600/30'
                    : 'text-surface-400 hover:text-white hover:bg-surface-800'
                }`}
              >
                <BarChart3 className="w-4 h-4" />
                <span>Usage Analytics</span>
              </Link>
            </div>
          )}
        </div>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-surface-800">
        <div className="flex items-center gap-2 text-xs text-surface-500">
          <div className="w-2 h-2 rounded-full bg-vault-500 animate-pulse" />
          <span>Connected</span>
        </div>
      </div>
    </aside>
  )
}

