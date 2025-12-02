// Document types
export type ProcessingStatus = 'pending' | 'processing' | 'completed' | 'failed'

export interface Document {
  id: string
  filename: string
  original_filename: string
  file_size: number
  mime_type: string
  status: ProcessingStatus
  status_message: string | null
  page_count: number | null
  word_count: number | null
  chunk_count: number
  summary: string | null
  created_at: string
  updated_at: string | null
  processed_at: string | null
}

export interface DocumentListResponse {
  documents: Document[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface DocumentUploadResponse {
  id: string
  filename: string
  original_filename: string
  file_size: number
  mime_type: string
  status: ProcessingStatus
  message: string
}

// Chat types
export interface DocumentSummary {
  id: string
  original_filename: string
  status: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
}

export interface Chat {
  id: string
  title: string | null
  documents: DocumentSummary[]
  created_at: string
  updated_at: string
}

export interface ChatDetail extends Chat {
  messages: Message[]
}

export interface ChatListResponse {
  chats: Chat[]
  total: number
  page: number
  page_size: number
}

export interface Source {
  document_id: string
  document_name: string
  chunk_content: string
  page_number: number | null
  similarity: number
}

export type QueryType = 'document_level' | 'follow_up' | 'chunk_retrieval' | 'mixed'
export type RetrievalStrategy = 'document_summaries' | 'conversation_history' | 'vector_search' | 'mixed'

export interface AskResponse {
  answer: string
  sources: Source[]
  message_id: string
  query_type: QueryType
  retrieval_strategy: RetrievalStrategy
}

// Admin types
export interface ChatUsage {
  chat_id: string
  chat_title: string | null
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  message_count: number
  created_at: string
  last_activity: string | null
}

export interface ChatUsageListResponse {
  chats: ChatUsage[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface UsageSummary {
  total_chats: number
  total_messages: number
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  total_embedding_tokens: number
}

