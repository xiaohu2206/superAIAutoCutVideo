// API客户端 - 处理与FastAPI后端的通信
import { invoke } from '@tauri-apps/api/core'

// API基础配置（默认端口，运行时可通过 configureBackend 动态覆盖）
const DEFAULT_HOST = '127.0.0.1'
const DEFAULT_PORT = 8000
const API_BASE_URL = `http://${DEFAULT_HOST}:${DEFAULT_PORT}`
const WS_BASE_URL = `ws://${DEFAULT_HOST}:${DEFAULT_PORT}`

// 类型定义
export interface BackendStatus {
  running: boolean
  port: number
  pid?: number
}

export interface ApiResponse<T = any> {
  message: string
  data?: T
  timestamp: string
}

export interface TaskStatus {
  task_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress: number
  message: string
}

export interface VideoProcessRequest {
  video_path: string
  output_path: string
  settings?: Record<string, any>
}

export interface WebSocketMessage {
  type: 'progress' | 'completed' | 'error' | 'heartbeat' | 'pong'
  task_id?: string
  progress?: number
  message?: string
  timestamp: string
  [key: string]: any
}

// HTTP客户端类
export class ApiClient {
  private baseUrl: string

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl
  }

  setBaseUrl(url: string) {
    this.baseUrl = url
  }

  // 通用请求方法
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`
    
    const defaultOptions: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    }

    try {
      const response = await fetch(url, defaultOptions)
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      const data = await response.json()
      return data
    } catch (error) {
      console.error(`API请求失败 [${endpoint}]:`, error)
      throw error
    }
  }

  // GET请求
  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' })
  }

  // POST请求
  async post<T>(endpoint: string, data?: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  // 测试连接
  async testConnection(): Promise<boolean> {
    try {
      await this.get('/api/hello')
      return true
    } catch {
      return false
    }
  }

  // 获取Hello消息
  async getHello(): Promise<ApiResponse> {
    return this.get<ApiResponse>('/api/hello')
  }

  // 获取服务状态
  async getStatus(): Promise<any> {
    return this.get('/api/status')
  }

  // 获取视频信息
  async getVideoInfo(videoPath: string): Promise<{ duration?: number; format?: string }> {
    return this.post('/api/video/info', { video_path: videoPath })
  }

  // 处理视频
  async processVideo(request: VideoProcessRequest): Promise<{ task_id: string }> {
    return this.post<{ task_id: string }>('/api/process', request)
  }

  // 获取任务状态
  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    return this.get<TaskStatus>(`/api/task/${taskId}`)
  }
}

// WebSocket客户端类
export class WebSocketClient {
  private ws: WebSocket | null = null
  private url: string
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000
  private listeners: Map<string, Set<(data: any) => void>> = new Map()

  constructor(url: string = `${WS_BASE_URL}/ws`) {
    this.url = url
  }

  setUrl(url: string) {
    this.url = url
  }

  // 连接WebSocket
  connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        console.log('正在连接WebSocket:', this.url)
        this.ws = new WebSocket(this.url)
        
        this.ws.onopen = () => {
          console.log('WebSocket连接已建立')
          this.reconnectAttempts = 0
          // 触发open事件
          this.emit('open', { connected: true })
          resolve()
        }

        this.ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data)
            this.handleMessage(message)
          } catch (error) {
            console.error('解析WebSocket消息失败:', error)
          }
        }

        this.ws.onclose = (event) => {
          console.log('WebSocket连接已关闭:', event.code, event.reason)
          // 触发close事件
          this.emit('close', { connected: false, code: event.code, reason: event.reason })
          this.handleReconnect()
        }

        this.ws.onerror = (error) => {
          console.error('WebSocket错误:', error)
          // 触发error事件
          this.emit('error', { error })
          reject(error)
        }
      } catch (error) {
        console.error('创建WebSocket连接失败:', error)
        reject(error)
      }
    })
  }

  // 处理消息
  private handleMessage(message: WebSocketMessage) {
    console.log('收到WebSocket消息:', message)
    
    // 触发对应类型的监听器
    const typeListeners = this.listeners.get(message.type)
    if (typeListeners) {
      typeListeners.forEach(listener => listener(message))
    }

    // 触发通用监听器
    const allListeners = this.listeners.get('*')
    if (allListeners) {
      allListeners.forEach(listener => listener(message))
    }
  }

  // 处理重连
  private handleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      console.log(`尝试重连WebSocket (${this.reconnectAttempts}/${this.maxReconnectAttempts})`)
      
      setTimeout(() => {
        this.connect().catch(error => {
          console.error('WebSocket重连失败:', error)
        })
      }, this.reconnectDelay * this.reconnectAttempts)
    } else {
      console.error('WebSocket重连次数已达上限')
    }
  }

  // 发送消息
  send(message: any): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    } else {
      console.warn('WebSocket未连接，无法发送消息')
    }
  }

  // 发送ping消息
  ping(): void {
    this.send({ type: 'ping', timestamp: new Date().toISOString() })
  }

  // 添加事件监听器
  on(type: string, listener: (data: any) => void): void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set())
    }
    this.listeners.get(type)!.add(listener)
  }

  // 移除事件监听器
  off(type: string, listener: (data: any) => void): void {
    const typeListeners = this.listeners.get(type)
    if (typeListeners) {
      typeListeners.delete(listener)
    }
  }

  // 触发事件
  private emit(type: string, data: any): void {
    const typeListeners = this.listeners.get(type)
    if (typeListeners) {
      typeListeners.forEach(listener => listener(data))
    }
  }

  // 断开连接
  disconnect(): void {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  // 获取连接状态
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

// Tauri命令包装器
export class TauriCommands {
  // 启动后端
  static async startBackend(): Promise<BackendStatus> {
    return invoke<BackendStatus>('start_backend')
  }

  // 停止后端
  static async stopBackend(): Promise<boolean> {
    return invoke<boolean>('stop_backend')
  }

  // 获取后端状态
  static async getBackendStatus(): Promise<BackendStatus> {
    return invoke<BackendStatus>('get_backend_status')
  }

  // 选择视频文件
  static async selectVideoFile(): Promise<{ path?: string; cancelled: boolean }> {
    return invoke('select_video_file')
  }

  // 选择输出目录
  static async selectOutputDirectory(): Promise<{ path?: string; cancelled: boolean }> {
    return invoke('select_output_directory')
  }

  // 获取应用信息
  static async getAppInfo(): Promise<Record<string, string>> {
    return invoke('get_app_info')
  }

  // 显示通知
  static async showNotification(title: string, body: string): Promise<void> {
    return invoke('show_notification', { title, body })
  }

  // 打开外部链接
  static async openExternalLink(url: string): Promise<void> {
    return invoke('open_external_link', { url })
  }
}

// 导出单例实例
export const apiClient = new ApiClient()
export const wsClient = new WebSocketClient()

// 运行时配置：根据端口动态更新 API 与 WS 端点
export function configureBackend(port: number, host: string = DEFAULT_HOST) {
  const httpBase = `http://${host}:${port}`
  const wsBase = `ws://${host}:${port}/ws`
  apiClient.setBaseUrl(httpBase)
  wsClient.setUrl(wsBase)
}

// 工具函数
export const utils = {
  // 格式化文件大小
  formatFileSize(bytes: number): string {
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    if (bytes === 0) return '0 B'
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i]
  },

  // 格式化时长
  formatDuration(seconds: number): string {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)
    
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`
  },

  // 延迟函数
  delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  },

  // 重试函数
  async retry<T>(
    fn: () => Promise<T>,
    maxAttempts: number = 3,
    delay: number = 1000
  ): Promise<T> {
    let lastError: Error
    
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      try {
        return await fn()
      } catch (error) {
        lastError = error as Error
        if (attempt < maxAttempts) {
          await this.delay(delay * attempt)
        }
      }
    }
    
    throw lastError!
  }
}