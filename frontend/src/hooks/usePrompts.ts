import { useCallback, useEffect, useState } from 'react'
import { promptsService } from '../services/promptsService'
import type { CreatePromptPayload, ProjectPromptSelection, PromptSummaryItem } from '../types/prompts'

export function usePrompts(projectId: string) {
  const [categories, setCategories] = useState<string[]>([])
  const [items, setItems] = useState<PromptSummaryItem[]>([])
  const [selection, setSelection] = useState<ProjectPromptSelection>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const defaultCategory = 'short_drama_narration'
  const featureKey = 'short_drama_narration:script_generation'

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [cats, list, sel] = await Promise.all([
        promptsService.getCategories(),
        promptsService.listPrompts(defaultCategory),
        promptsService.getProjectSelection(projectId),
      ])
      setCategories(cats)
      setItems(list)
      setSelection(sel || {})
    } catch (e: any) {
      setError(e?.message || '加载提示词失败')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    if (projectId) fetchAll()
  }, [projectId, fetchAll])

  const setProjectSelection = useCallback(async (type: 'official' | 'user', key_or_id: string) => {
    const sel = await promptsService.setProjectSelection(projectId, featureKey, { type, key_or_id })
    setSelection(sel)
  }, [projectId])

  const createOrUpdateTemplate = useCallback(async (payload: CreatePromptPayload & { id?: string }) => {
    if (payload.id) {
      const d = await promptsService.updatePrompt(payload.id, payload)
      await fetchAll()
      return d
    }
    const d = await promptsService.createPrompt(payload)
    await fetchAll()
    return d
  }, [fetchAll])

  const deleteTemplate = useCallback(async (id: string) => {
    await promptsService.deletePrompt(id)
    await fetchAll()
  }, [fetchAll])

  const getPromptDetail = useCallback(async (key_or_id: string) => {
    return promptsService.getPromptDetail(key_or_id)
  }, [])

  return {
    categories,
    items,
    selection,
    loading,
    error,
    featureKey,
    defaultCategory,
    fetchAll,
    setProjectSelection,
    createOrUpdateTemplate,
    deleteTemplate,
    getPromptDetail,
    renderPreview: promptsService.renderPreview.bind(promptsService),
    validateTemplate: promptsService.validateTemplate.bind(promptsService),
  }
}
