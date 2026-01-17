import { apiClient } from "./clients"

export type LogType = "log" | "progress" | "error" | "success" | "ws_text" | string

export interface LogItem {
  id: number
  timestamp: string
  type: LogType
  scope?: string
  project_id?: string | null
  message?: string
  detail?: string
  error?: string
  channel?: string
  [key: string]: any
}

export interface LogsListResponse {
  items: LogItem[]
  next_after_id: number | null
}

const normalizeLogsListResponse = (resp: any): LogsListResponse => {
  const items = Array.isArray(resp?.items) ? resp.items : Array.isArray(resp?.data?.items) ? resp.data.items : []
  const nextAfterId =
    typeof resp?.next_after_id === "number" || resp?.next_after_id === null
      ? resp.next_after_id
      : typeof resp?.data?.next_after_id === "number" || resp?.data?.next_after_id === null
        ? resp.data.next_after_id
        : null
  return { items, next_after_id: nextAfterId }
}

const buildQuery = (params: Record<string, any>) => {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return
    search.set(k, String(v))
  })
  const s = search.toString()
  return s ? `?${s}` : ""
}

export const logsService = {
  async getGlobalLogs(params?: { after_id?: number; limit?: number }): Promise<LogsListResponse> {
    const q = buildQuery(params || {})
    const resp = await apiClient.get<any>(`/api/logs${q}`)
    return normalizeLogsListResponse(resp)
  },

  async clearGlobalLogs(): Promise<void> {
    await apiClient.post(`/api/logs/clear`)
  },

  async getProjectLogs(projectId: string, params?: { after_id?: number; limit?: number }): Promise<LogsListResponse> {
    const q = buildQuery(params || {})
    const resp = await apiClient.get<any>(`/api/projects/${encodeURIComponent(projectId)}/logs${q}`)
    return normalizeLogsListResponse(resp)
  },

  async clearProjectLogs(projectId: string): Promise<void> {
    await apiClient.post(`/api/projects/${encodeURIComponent(projectId)}/logs/clear`)
  },

  createGlobalLogsEventSource(params?: { after_id?: number }) {
    const base = apiClient.getBaseUrl()
    const q = buildQuery(params || {})
    return new EventSource(`${base}/api/logs/stream${q}`)
  },

  createProjectLogsEventSource(projectId: string, params?: { after_id?: number }) {
    const base = apiClient.getBaseUrl()
    const q = buildQuery(params || {})
    return new EventSource(`${base}/api/projects/${encodeURIComponent(projectId)}/logs/stream${q}`)
  },
}

export default logsService

