import React, { useState } from 'react'
import { ChevronDown, ChevronUp, Activity, Wifi, Server, Clock } from 'lucide-react'
import { WebSocketMessage } from '../api/client'

interface StatusPanelProps {
  messages: WebSocketMessage[]
  backendStatus: {
    running: boolean
    port: number
    pid?: number
  }
  connections: {
    api: boolean
    websocket: boolean
  }
}

const StatusPanel: React.FC<StatusPanelProps> = ({
  messages,
  backendStatus,
  connections
}) => {
  const [isExpanded, setIsExpanded] = useState(false)
  const [selectedMessageType, setSelectedMessageType] = useState<string>('all')

  // 获取消息类型统计
  const messageStats = messages.reduce((acc, msg) => {
    acc[msg.type] = (acc[msg.type] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  // 过滤消息
  const filteredMessages = selectedMessageType === 'all' 
    ? messages 
    : messages.filter(msg => msg.type === selectedMessageType)

  // 格式化时间
  const formatTime = (timestamp: string) => {
    try {
      return new Date(timestamp).toLocaleTimeString('zh-CN', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    } catch {
      return timestamp
    }
  }

  // 获取消息类型图标
  const getMessageIcon = (type: string) => {
    switch (type) {
      case 'heartbeat':
        return <Activity className="h-4 w-4 text-green-500" />
      case 'progress':
        return <Clock className="h-4 w-4 text-blue-500" />
      case 'completed':
        return <div className="h-4 w-4 bg-green-500 rounded-full" />
      case 'error':
        return <div className="h-4 w-4 bg-red-500 rounded-full" />
      default:
        return <div className="h-4 w-4 bg-gray-400 rounded-full" />
    }
  }

  // 获取消息类型颜色
  const getMessageTypeColor = (type: string) => {
    switch (type) {
      case 'heartbeat':
        return 'text-green-600 bg-green-50'
      case 'progress':
        return 'text-blue-600 bg-blue-50'
      case 'completed':
        return 'text-green-600 bg-green-50'
      case 'error':
        return 'text-red-600 bg-red-50'
      case 'pong':
        return 'text-purple-600 bg-purple-50'
      default:
        return 'text-gray-600 bg-gray-50'
    }
  }

  return (
    <div className="bg-white rounded-lg shadow-md overflow-hidden">
      {/* 面板头部 */}
      <div 
        className="px-6 py-4 bg-gray-50 border-b cursor-pointer hover:bg-gray-100 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Activity className="h-5 w-5 text-gray-600" />
            <h3 className="text-lg font-medium text-gray-900">系统状态监控</h3>
            <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs font-medium rounded-full">
              {messages.length} 条消息
            </span>
          </div>
          {isExpanded ? (
            <ChevronUp className="h-5 w-5 text-gray-400" />
          ) : (
            <ChevronDown className="h-5 w-5 text-gray-400" />
          )}
        </div>
      </div>

      {/* 状态概览 */}
      <div className="px-6 py-4 border-b bg-gray-50">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* 后端状态 */}
          <div className="flex items-center space-x-3">
            <Server className={`h-5 w-5 ${backendStatus.running ? 'text-green-500' : 'text-red-500'}`} />
            <div>
              <p className="text-sm font-medium text-gray-900">后端服务</p>
              <p className={`text-xs ${backendStatus.running ? 'text-green-600' : 'text-red-600'}`}>
                {backendStatus.running ? `运行中 :${backendStatus.port}` : '已停止'}
              </p>
            </div>
          </div>

          {/* API连接状态 */}
          <div className="flex items-center space-x-3">
            <div className={`h-5 w-5 rounded-full ${connections.api ? 'bg-green-500' : 'bg-red-500'}`} />
            <div>
              <p className="text-sm font-medium text-gray-900">HTTP API</p>
              <p className={`text-xs ${connections.api ? 'text-green-600' : 'text-red-600'}`}>
                {connections.api ? '已连接' : '未连接'}
              </p>
            </div>
          </div>

          {/* WebSocket连接状态 */}
          <div className="flex items-center space-x-3">
            <Wifi className={`h-5 w-5 ${connections.websocket ? 'text-green-500' : 'text-red-500'}`} />
            <div>
              <p className="text-sm font-medium text-gray-900">WebSocket</p>
              <p className={`text-xs ${connections.websocket ? 'text-green-600' : 'text-red-600'}`}>
                {connections.websocket ? '已连接' : '未连接'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 展开的内容 */}
      {isExpanded && (
        <div className="px-6 py-4">
          {/* 消息类型过滤器 */}
          <div className="mb-4">
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => setSelectedMessageType('all')}
                className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                  selectedMessageType === 'all'
                    ? 'bg-blue-100 text-blue-800'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                全部 ({messages.length})
              </button>
              {Object.entries(messageStats).map(([type, count]) => (
                <button
                  key={type}
                  onClick={() => setSelectedMessageType(type)}
                  className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                    selectedMessageType === type
                      ? getMessageTypeColor(type)
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {type} ({count})
                </button>
              ))}
            </div>
          </div>

          {/* 消息列表 */}
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {filteredMessages.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <Activity className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>暂无消息</p>
              </div>
            ) : (
              filteredMessages.slice(-20).reverse().map((message, index) => (
                <div
                  key={`${message.timestamp}-${index}`}
                  className="flex items-start space-x-3 p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  {getMessageIcon(message.type)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2 mb-1">
                      <span className={`px-2 py-0.5 text-xs font-medium rounded ${getMessageTypeColor(message.type)}`}>
                        {message.type}
                      </span>
                      <span className="text-xs text-gray-500">
                        {formatTime(message.timestamp)}
                      </span>
                      {message.task_id && (
                        <span className="text-xs text-gray-400">
                          #{message.task_id.slice(-6)}
                        </span>
                      )}
                    </div>
                    
                    {message.message && (
                      <p className="text-sm text-gray-700 mb-1">{message.message}</p>
                    )}
                    
                    {message.progress !== undefined && (
                      <div className="flex items-center space-x-2">
                        <div className="flex-1 bg-gray-200 rounded-full h-1.5">
                          <div
                            className="bg-blue-600 h-1.5 rounded-full transition-all duration-300"
                            style={{ width: `${message.progress}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500">{message.progress}%</span>
                      </div>
                    )}
                    
                    {/* 显示其他字段 */}
                    {Object.entries(message).map(([key, value]) => {
                      if (['type', 'timestamp', 'message', 'progress', 'task_id'].includes(key)) {
                        return null
                      }
                      return (
                        <div key={key} className="text-xs text-gray-500 mt-1">
                          <span className="font-medium">{key}:</span> {String(value)}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))
            )}
          </div>

          {filteredMessages.length > 20 && (
            <div className="mt-3 text-center">
              <p className="text-xs text-gray-500">
                显示最近 20 条消息，共 {filteredMessages.length} 条
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default StatusPanel