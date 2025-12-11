import type { CreatePromptPayload, ProjectPromptSelection, PromptDetail, PromptSummaryItem, RenderPreviewResponse } from '../types/prompts'
import { apiClient } from './clients'

export class PromptsService {
  async getCategories(): Promise<string[]> {
    const resp = await apiClient.get<{ data: string[] }>(`/api/prompts/categories`)
    return resp.data
  }

  async listPrompts(category?: string): Promise<PromptSummaryItem[]> {
    const qs = category ? `?category=${encodeURIComponent(category)}` : ''
    const resp = await apiClient.get<{ data: PromptSummaryItem[] }>(`/api/prompts${qs}`)
    return resp.data
  }

  async getPromptDetail(key_or_id: string): Promise<PromptDetail> {
    const resp = await apiClient.get<{ data: PromptDetail }>(`/api/prompts/${encodeURIComponent(key_or_id)}`)
    return resp.data
  }

  async renderPreview(key_or_id: string, variables?: Record<string, any>): Promise<RenderPreviewResponse> {
    const resp = await apiClient.post<{ data: { messages: RenderPreviewResponse['messages'] } }>(`/api/prompts/${encodeURIComponent(key_or_id)}/render-preview`, { variables })
    return { messages: resp.data.messages }
  }

  async createPrompt(payload: CreatePromptPayload): Promise<PromptDetail> {
    const resp = await apiClient.post<{ data: PromptDetail }>(`/api/prompts`, payload)
    return resp.data
  }

  async updatePrompt(id: string, payload: CreatePromptPayload): Promise<PromptDetail> {
    const resp = await apiClient.put<{ data: PromptDetail }>(`/api/prompts/${encodeURIComponent(id)}`, payload)
    return resp.data
  }

  async deletePrompt(id: string): Promise<boolean> {
    const resp = await apiClient.delete<{ data: { deleted: boolean } }>(`/api/prompts/${encodeURIComponent(id)}`)
    return !!resp.data?.deleted
  }

  async validateTemplate(template: string, required_vars: string[]): Promise<{ placeholders: string[]; missing: string[]; extra: string[] }> {
    const resp = await apiClient.post<{ data: { placeholders: string[]; missing: string[]; extra: string[] } }>(`/api/prompts/validate`, { template, required_vars })
    return resp.data
  }

  async setProjectSelection(projectId: string, featureKey: string, selection: { type: 'official' | 'user'; key_or_id: string }): Promise<ProjectPromptSelection> {
    const resp = await apiClient.post<{ data: any }>(`/api/prompts/projects/${projectId}/prompts/select`, { feature_key: featureKey, selection })
    return (resp.data?.prompt_selection || {}) as ProjectPromptSelection
  }

  async getProjectSelection(projectId: string): Promise<ProjectPromptSelection> {
    const resp = await apiClient.get<{ data: ProjectPromptSelection }>(`/api/prompts/projects/${projectId}/prompts/selection`)
    return resp.data
  }
}

export const promptsService = new PromptsService()
