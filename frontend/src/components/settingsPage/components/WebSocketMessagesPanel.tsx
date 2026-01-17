import { Activity, AlertCircle, CheckCircle, Clock } from "lucide-react"
import React, { useMemo, useState } from "react"
import type { WebSocketMessage } from "../../../services/clients"

const formatTime = (timestamp: string) => {
  try {
    return new Date(timestamp).toLocaleTimeString("zh-CN", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
  } catch {
    return timestamp
  }
}

const getMessageIcon = (type: string) => {
  switch (type) {
    case "heartbeat":
      return <Activity className="h-4 w-4 text-green-500" />
    case "progress":
      return <Clock className="h-4 w-4 text-blue-500" />
    case "completed":
      return <CheckCircle className="h-4 w-4 text-green-500" />
    case "error":
      return <AlertCircle className="h-4 w-4 text-red-500" />
    default:
      return <div className="h-4 w-4 bg-gray-400 rounded-full" />
  }
}

const getMessageTypeColor = (type: string) => {
  switch (type) {
    case "heartbeat":
      return "text-green-700 bg-green-50 ring-1 ring-green-200"
    case "progress":
      return "text-blue-700 bg-blue-50 ring-1 ring-blue-200"
    case "completed":
      return "text-green-700 bg-green-50 ring-1 ring-green-200"
    case "error":
      return "text-red-700 bg-red-50 ring-1 ring-red-200"
    case "pong":
      return "text-purple-700 bg-purple-50 ring-1 ring-purple-200"
    default:
      return "text-gray-700 bg-gray-50 ring-1 ring-gray-200"
  }
}

export interface WebSocketMessagesPanelProps {
  messages: WebSocketMessage[]
}

export const WebSocketMessagesPanel: React.FC<WebSocketMessagesPanelProps> = ({ messages }) => {
  const [selectedMessageType, setSelectedMessageType] = useState<string>("all")

  const messageStats = useMemo(() => {
    return messages.reduce((acc, msg) => {
      acc[msg.type] = (acc[msg.type] || 0) + 1
      return acc
    }, {} as Record<string, number>)
  }, [messages])

  const filteredMessages = useMemo(() => {
    return selectedMessageType === "all" ? messages : messages.filter((m) => m.type === selectedMessageType)
  }, [messages, selectedMessageType])

  return (
    <div className="rounded-lg border bg-white overflow-hidden">
      <div className="px-4 py-3 border-b bg-gradient-to-r from-gray-50 to-white flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="text-sm font-medium text-gray-900">WebSocket 事件</div>
          <span className="px-2 py-0.5 text-xs font-medium rounded-full ring-1 bg-blue-50 text-blue-700 ring-blue-200">
            {messages.length} 条
          </span>
        </div>
      </div>

      <div className="px-4 py-3 border-b bg-white">
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setSelectedMessageType("all")}
            className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
              selectedMessageType === "all"
                ? "bg-blue-100 text-blue-800 ring-1 ring-blue-200"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 ring-1 ring-gray-200"
            }`}
          >
            全部 ({messages.length})
          </button>
          {Object.entries(messageStats).map(([type, count]) => (
            <button
              key={type}
              onClick={() => setSelectedMessageType(type)}
              className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${
                selectedMessageType === type ? getMessageTypeColor(type) : "bg-gray-100 text-gray-600 hover:bg-gray-200 ring-1 ring-gray-200"
              }`}
            >
              {type} ({count})
            </button>
          ))}
        </div>
      </div>

      <div className="max-h-80 overflow-y-auto divide-y divide-gray-100 bg-white">
        {filteredMessages.length === 0 ? (
          <div className="text-center py-10 text-gray-500">
            <Activity className="h-8 w-8 mx-auto mb-2 opacity-60" />
            <p>暂无消息</p>
          </div>
        ) : (
          filteredMessages
            .slice(-30)
            .reverse()
            .map((message, index) => (
              <div key={`${message.timestamp}-${index}`} className="flex items-start space-x-3 p-3 hover:bg-gray-50 transition-colors">
                {getMessageIcon(message.type)}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center space-x-2 mb-1">
                    <span className={`px-2 py-0.5 text-xs font-medium rounded-full ${getMessageTypeColor(message.type)}`}>{message.type}</span>
                    <span className="text-xs text-gray-500">{formatTime(message.timestamp)}</span>
                    {message.task_id && <span className="text-xs text-gray-400">#{message.task_id.slice(-6)}</span>}
                  </div>

                  {message.message && <p className="text-sm text-gray-700 mb-1 break-words">{message.message}</p>}

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

                  {Object.entries(message).map(([key, value]) => {
                    if (["type", "timestamp", "message", "progress", "task_id"].includes(key)) return null
                    return (
                      <div key={key} className="text-xs text-gray-500 mt-1 break-words">
                        <span className="font-medium">{key}:</span> {String(value)}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))
        )}
      </div>

      {filteredMessages.length > 30 && (
        <div className="px-4 py-2 text-center bg-white border-t">
          <p className="text-xs text-gray-500">显示最近 30 条消息，共 {filteredMessages.length} 条</p>
        </div>
      )}
    </div>
  )
}

export default WebSocketMessagesPanel

