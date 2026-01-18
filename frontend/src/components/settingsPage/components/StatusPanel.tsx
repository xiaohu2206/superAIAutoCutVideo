import { Activity, AlertTriangle, CheckCircle, Play, RefreshCw, Server, Wifi, X } from 'lucide-react'
import React, { useState } from 'react'
import { WebSocketMessage } from '../../../services/clients'
import healthService, { IntegrationTestResult } from '../../../services/healthService'
import LogConsolePanel from './LogConsolePanel'

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
  onRefresh?: () => Promise<void> | void
}

const StatusPanel: React.FC<StatusPanelProps> = ({
  messages,
  backendStatus,
  connections,
  onRefresh
}) => {
  const [isTesting, setIsTesting] = useState(false)
  const [testResult, setTestResult] = useState<IntegrationTestResult | null>(null)
  const [snapshotBackendStatus, setSnapshotBackendStatus] = useState(backendStatus)
  const [snapshotConnections, setSnapshotConnections] = useState(connections)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const handleRunDiagnostics = async () => {
    if (isTesting) return
    setIsTesting(true)
    setTestResult(null)
    try {
      const response = await healthService.testIntegrations()
      if (response.success) {
        setTestResult(response.data)
      } else {
        console.error('Test failed', response.message)
      }
    } catch (e) {
      console.error('Test failed', e)
    } finally {
      setIsTesting(false)
    }
  }

  const handleRefreshStatus = async () => {
    if (isRefreshing) return
    setIsRefreshing(true)
    try {
      if (onRefresh) {
        await Promise.resolve(onRefresh())
      }
      setSnapshotBackendStatus(backendStatus)
      setSnapshotConnections(connections)
    } finally {
      setIsRefreshing(false)
    }
  }

  return (
    <div className="bg-white/80 backdrop-blur rounded-xl border shadow-sm overflow-hidden">
      {/* 面板头部 */}
      <div className="px-6 py-4 bg-gradient-to-r from-gray-50 to-white border-b">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Activity className="h-5 w-5 text-gray-600" />
            <h3 className="text-lg font-medium text-gray-900">系统状态监控</h3>
            <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs font-medium rounded-full ring-1 ring-blue-200">
              {messages.length} 条消息
            </span>
            <button
              onClick={() => handleRunDiagnostics()}
              disabled={isTesting}
              className={`ml-2 px-3 py-1 text-xs font-medium rounded-full flex items-center space-x-1 transition-colors ${
                isTesting
                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  : 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200 ring-1 ring-indigo-200'
              }`}
              title="测试大模型、TTS 与 ASR 连通性"
            >
              <Play className="h-3 w-3" />
              <span>{isTesting ? '自检中...' : '一键自检'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* 状态概览 */}
      <div className="px-6 py-4 border-b bg-white">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
          {/* 后端状态 */}
          <div className="flex items-center space-x-3 rounded-md px-2 py-2 hover:bg-gray-50 transition-colors">
            <Server className={`h-5 w-5 ${snapshotBackendStatus.running ? 'text-green-500' : 'text-red-500'}`} />
            <div>
              <p className="text-sm font-medium text-gray-900">后端服务</p>
              <p className={`text-xs ${snapshotBackendStatus.running ? 'text-green-600' : 'text-red-600'}`}>
                {snapshotBackendStatus.running ? `运行中 :${snapshotBackendStatus.port}` : '已停止'}
              </p>
            </div>
          </div>

          {/* API连接状态 */}
          <div className="flex items-center space-x-3 rounded-md px-2 py-2 hover:bg-gray-50 transition-colors">
            <div className={`h-5 w-5 rounded-full ${snapshotConnections.api ? 'bg-green-500' : 'bg-red-500'}`} />
            <div>
              <p className="text-sm font-medium text-gray-900">HTTP API</p>
              <p className={`text-xs ${snapshotConnections.api ? 'text-green-600' : 'text-red-600'}`}>
                {snapshotConnections.api ? '已连接' : '未连接'}
              </p>
            </div>
          </div>

          {/* WebSocket连接状态 */}
          <div className="flex items-center space-x-3 rounded-md px-2 py-2 hover:bg-gray-50 transition-colors">
            <Wifi className={`h-5 w-5 ${snapshotConnections.websocket ? 'text-green-500' : 'text-red-500'}`} />
            <div>
              <p className="text-sm font-medium text-gray-900">WebSocket</p>
              <p className={`text-xs ${snapshotConnections.websocket ? 'text-green-600' : 'text-red-600'}`}>
                {snapshotConnections.websocket ? '已连接' : '未连接'}
              </p>
            </div>
          </div>
        </div>
        <div className="mt-3 flex justify-end">
          <button
            onClick={handleRefreshStatus}
            disabled={isRefreshing}
            className={`px-3 py-1 text-xs font-medium rounded-full flex items-center space-x-1 ring-1 transition-colors ${
              isRefreshing
                ? 'bg-gray-100 text-gray-400 ring-gray-200 cursor-not-allowed'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200 ring-gray-200'
            }`}
            title="刷新状态概览"
          >
            <RefreshCw className="h-3 w-3" />
            <span>{isRefreshing ? '刷新中...' : '刷新'}</span>
          </button>
        </div>
      </div>

      {/* 诊断结果 */}
      {testResult && (
        <div className="px-6 py-4 border-b bg-gray-50">
            <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-medium text-gray-900 flex items-center">
                    <Activity className="h-4 w-4 mr-2 text-indigo-500"/>
                    组件自检报告
                </h4>
                <button 
                    onClick={() => setTestResult(null)}
                    className="text-gray-400 hover:text-gray-600"
                >
                    <X className="h-4 w-4" />
                </button>
            </div>
            
            <div className="space-y-3">
                {/* 文案模型状态 */}
                <div className={`p-3 rounded-lg border ${
                    testResult.content_model.status === 'ok' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
                }`}>
                    <div className="flex items-start">
                        {testResult.content_model.status === 'ok' ? (
                            <CheckCircle className="h-5 w-5 text-green-500 mt-0.5 mr-3 flex-shrink-0" />
                        ) : (
                            <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5 mr-3 flex-shrink-0" />
                        )}
                        <div>
                            <p className={`text-sm font-medium ${
                                testResult.content_model.status === 'ok' ? 'text-green-800' : 'text-red-800'
                            }`}>
                                文案生成模型
                            </p>
                            <p className={`text-xs mt-1 ${
                                testResult.content_model.status === 'ok' ? 'text-green-600' : 'text-red-600'
                            }`}>
                                {testResult.content_model.message}
                            </p>
                        </div>
                    </div>
                </div>

                {/* TTS状态 */}
                <div className={`p-3 rounded-lg border ${
                    testResult.tts.status === 'ok' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
                }`}>
                    <div className="flex items-start">
                        {testResult.tts.status === 'ok' ? (
                            <CheckCircle className="h-5 w-5 text-green-500 mt-0.5 mr-3 flex-shrink-0" />
                        ) : (
                            <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5 mr-3 flex-shrink-0" />
                        )}
                        <div>
                            <p className={`text-sm font-medium ${
                                testResult.tts.status === 'ok' ? 'text-green-800' : 'text-red-800'
                            }`}>
                                语音合成引擎 (TTS)
                            </p>
                            <p className={`text-xs mt-1 ${
                                testResult.tts.status === 'ok' ? 'text-green-600' : 'text-red-600'
                            }`}>
                                {testResult.tts.message}
                            </p>
                        </div>
                    </div>
                </div>

                {/* ASR状态 */}
                <div className={`p-3 rounded-lg border ${
                    testResult.asr.status === 'ok' ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
                }`}>
                    <div className="flex items-start">
                        {testResult.asr.status === 'ok' ? (
                            <CheckCircle className="h-5 w-5 text-green-500 mt-0.5 mr-3 flex-shrink-0" />
                        ) : (
                            <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5 mr-3 flex-shrink-0" />
                        )}
                        <div>
                            <p className={`text-sm font-medium ${
                                testResult.asr.status === 'ok' ? 'text-green-800' : 'text-red-800'
                            }`}>
                                语音识别引擎 (ASR)
                            </p>
                            <p className={`text-xs mt-1 ${
                                testResult.asr.status === 'ok' ? 'text-green-600' : 'text-red-600'
                            }`}>
                                {testResult.asr.message}
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
      )}

      <div className="px-6 py-4 space-y-4">
        <LogConsolePanel enabled />
        {/* <WebSocketMessagesPanel messages={messages} /> */}
      </div>
    </div>
  )
}

export default StatusPanel
