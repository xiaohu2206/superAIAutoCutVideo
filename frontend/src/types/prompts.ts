export interface PromptSummaryItem {
  id_or_key: string
  name: string
  origin: 'official' | 'user'
  category?: string
  tags?: string[]
}

export interface PromptDetail {
  id_or_key: string
  name: string
  category?: string
  origin: 'official' | 'user'
  template: string
  variables: string[]
  system_prompt?: string
  tags?: string[]
  version?: string
}

export interface CreatePromptPayload {
  id?: string
  name: string
  category: string
  description?: string
  template: string
  variables?: string[]
  system_prompt?: string
  tags?: string[]
  version?: string
  enabled?: boolean
}

export interface RenderPreviewResponse {
  messages: { role: string; content: string }[]
}

export interface ProjectPromptSelection {
  [featureKey: string]: { type: 'official' | 'user'; key_or_id: string }
}
