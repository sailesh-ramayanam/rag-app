import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  BarChart3,
  MessageSquare,
  Coins,
  ArrowUpRight,
  ArrowDownRight,
  ChevronLeft,
  ChevronRight,
  Loader2,
  TrendingUp,
} from 'lucide-react'
import { api } from '../api/client'

function formatNumber(num: number): string {
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`
  return num.toString()
}

function formatDate(dateString: string | null): string {
  if (!dateString) return 'Never'
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

interface StatCardProps {
  title: string
  value: string | number
  icon: React.ElementType
  trend?: 'up' | 'down'
  subtitle?: string
}

function StatCard({ title, value, icon: Icon, trend, subtitle }: StatCardProps) {
  return (
    <div className="p-5 rounded-xl bg-surface-800/50 border border-surface-700">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-surface-400 mb-1">{title}</p>
          <p className="text-2xl font-semibold text-white">{value}</p>
          {subtitle && <p className="text-xs text-surface-500 mt-1">{subtitle}</p>}
        </div>
        <div className="w-10 h-10 rounded-lg bg-vault-500/10 flex items-center justify-center">
          <Icon className="w-5 h-5 text-vault-400" />
        </div>
      </div>
      {trend && (
        <div className={`flex items-center gap-1 mt-3 text-xs ${
          trend === 'up' ? 'text-vault-400' : 'text-red-400'
        }`}>
          {trend === 'up' ? (
            <ArrowUpRight className="w-3 h-3" />
          ) : (
            <ArrowDownRight className="w-3 h-3" />
          )}
          <span>vs last period</span>
        </div>
      )}
    </div>
  )
}

export default function AdminPage() {
  const [page, setPage] = useState(1)
  const pageSize = 10

  // Fetch usage summary
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['usage-summary'],
    queryFn: () => api.getUsageSummary(),
  })

  // Fetch chat usage
  const { data: usage, isLoading: usageLoading } = useQuery({
    queryKey: ['chat-usage', page],
    queryFn: () => api.getChatUsage(page, pageSize),
  })

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <header className="flex-shrink-0 p-6 border-b border-surface-800">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-vault-500 to-vault-600 flex items-center justify-center">
            <BarChart3 className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-white">Usage Analytics</h1>
            <p className="text-surface-400 text-sm">Monitor token usage across chats</p>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          {summaryLoading ? (
            [...Array(4)].map((_, i) => (
              <div key={i} className="h-28 rounded-xl bg-surface-800 animate-pulse" />
            ))
          ) : summary ? (
            <>
              <StatCard
                title="Total Chats"
                value={summary.total_chats}
                icon={MessageSquare}
              />
              <StatCard
                title="Total Messages"
                value={formatNumber(summary.total_messages)}
                icon={TrendingUp}
              />
              <StatCard
                title="Chat Tokens"
                value={formatNumber(summary.total_tokens)}
                icon={Coins}
                subtitle={`${formatNumber(summary.total_input_tokens)} in / ${formatNumber(summary.total_output_tokens)} out`}
              />
              <StatCard
                title="Embedding Tokens"
                value={formatNumber(summary.total_embedding_tokens)}
                icon={BarChart3}
              />
            </>
          ) : null}
        </div>

        {/* Usage Table */}
        <div className="bg-surface-800/30 rounded-xl border border-surface-700 overflow-hidden">
          <div className="p-4 border-b border-surface-700">
            <h2 className="font-medium text-white">Chat Token Usage</h2>
          </div>

          {usageLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 text-vault-400 animate-spin" />
            </div>
          ) : usage?.chats.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <BarChart3 className="w-12 h-12 text-surface-600 mb-3" />
              <p className="text-surface-400">No usage data yet</p>
              <p className="text-surface-500 text-sm">Start some chats to see analytics</p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-surface-700 text-left">
                      <th className="px-4 py-3 text-xs font-medium text-surface-400 uppercase tracking-wider">
                        Chat
                      </th>
                      <th className="px-4 py-3 text-xs font-medium text-surface-400 uppercase tracking-wider text-right">
                        Messages
                      </th>
                      <th className="px-4 py-3 text-xs font-medium text-surface-400 uppercase tracking-wider text-right">
                        Input Tokens
                      </th>
                      <th className="px-4 py-3 text-xs font-medium text-surface-400 uppercase tracking-wider text-right">
                        Output Tokens
                      </th>
                      <th className="px-4 py-3 text-xs font-medium text-surface-400 uppercase tracking-wider text-right">
                        Total Tokens
                      </th>
                      <th className="px-4 py-3 text-xs font-medium text-surface-400 uppercase tracking-wider text-right">
                        Last Activity
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-surface-700/50">
                    {usage?.chats.map((chat, index) => (
                      <tr
                        key={chat.chat_id}
                        className="hover:bg-surface-700/30 transition-colors animate-fade-in"
                        style={{ animationDelay: `${index * 30}ms` }}
                      >
                        <td className="px-4 py-3">
                          <Link
                            to={`/chat/${chat.chat_id}`}
                            className="flex items-center gap-2 text-vault-400 hover:text-vault-300 transition-colors"
                          >
                            <MessageSquare className="w-4 h-4" />
                            <span className="font-medium truncate max-w-[200px]">
                              {chat.chat_title || `Chat ${chat.chat_id.slice(0, 8)}...`}
                            </span>
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-right text-surface-300 font-mono text-sm">
                          {chat.message_count}
                        </td>
                        <td className="px-4 py-3 text-right text-surface-300 font-mono text-sm">
                          {formatNumber(chat.total_input_tokens)}
                        </td>
                        <td className="px-4 py-3 text-right text-surface-300 font-mono text-sm">
                          {formatNumber(chat.total_output_tokens)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-vault-500/10 text-vault-400">
                            {formatNumber(chat.total_tokens)}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right text-surface-500 text-sm">
                          {formatDate(chat.last_activity)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {usage && usage.total_pages > 1 && (
                <div className="flex items-center justify-between px-4 py-3 border-t border-surface-700">
                  <p className="text-sm text-surface-400">
                    Page {usage.page} of {usage.total_pages}
                  </p>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className="p-2 rounded-lg text-surface-400 hover:text-white hover:bg-surface-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => setPage((p) => Math.min(usage.total_pages, p + 1))}
                      disabled={page === usage.total_pages}
                      className="p-2 rounded-lg text-surface-400 hover:text-white hover:bg-surface-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

