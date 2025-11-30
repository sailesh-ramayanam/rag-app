const API_BASE = '/api/v1'

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new ApiError(response.status, error.detail || error.message || 'Request failed')
  }
  return response.json()
}

export const api = {
  // Documents
  async getDocuments(page = 1, pageSize = 50) {
    const response = await fetch(`${API_BASE}/documents/?page=${page}&page_size=${pageSize}`)
    return handleResponse<import('../types').DocumentListResponse>(response)
  },

  async getDocument(id: string) {
    const response = await fetch(`${API_BASE}/documents/${id}`)
    return handleResponse<import('../types').Document>(response)
  },

  async uploadDocument(file: File) {
    const formData = new FormData()
    formData.append('file', file)
    const response = await fetch(`${API_BASE}/documents/upload`, {
      method: 'POST',
      body: formData,
    })
    return handleResponse<import('../types').DocumentUploadResponse>(response)
  },

  async deleteDocument(id: string) {
    const response = await fetch(`${API_BASE}/documents/${id}`, {
      method: 'DELETE',
    })
    return handleResponse<{ message: string }>(response)
  },

  async downloadDocument(id: string, filename: string) {
    const response = await fetch(`${API_BASE}/documents/${id}/download`)
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Download failed' }))
      throw new ApiError(response.status, error.detail || 'Download failed')
    }
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  },

  // Chats
  async getChats(page = 1, pageSize = 100) {
    const response = await fetch(`${API_BASE}/chats/?page=${page}&page_size=${pageSize}`)
    return handleResponse<import('../types').ChatListResponse>(response)
  },

  async getChat(id: string) {
    const response = await fetch(`${API_BASE}/chats/${id}`)
    return handleResponse<import('../types').ChatDetail>(response)
  },

  async createChat(documentIds: string[], title?: string) {
    const response = await fetch(`${API_BASE}/chats/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_ids: documentIds, title }),
    })
    return handleResponse<import('../types').Chat>(response)
  },

  async sendMessage(chatId: string, question: string, topK = 5) {
    const response = await fetch(`${API_BASE}/chats/${chatId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, top_k: topK }),
    })
    return handleResponse<import('../types').AskResponse>(response)
  },

  async deleteChat(id: string) {
    const response = await fetch(`${API_BASE}/chats/${id}`, {
      method: 'DELETE',
    })
    return handleResponse<{ message: string }>(response)
  },

  // Admin
  async getChatUsage(page = 1, pageSize = 20) {
    const response = await fetch(`${API_BASE}/admin/usage/chats?page=${page}&page_size=${pageSize}`)
    return handleResponse<import('../types').ChatUsageListResponse>(response)
  },

  async getUsageSummary() {
    const response = await fetch(`${API_BASE}/admin/usage/summary`)
    return handleResponse<import('../types').UsageSummary>(response)
  },
}

export { ApiError }

