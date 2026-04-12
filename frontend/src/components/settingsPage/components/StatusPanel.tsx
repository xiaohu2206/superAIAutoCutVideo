import { Activity, AlertTriangle, CheckCircle, X } from 'lucide-react'
import React, { useState } from 'react'
import { WebSocketMessage } from '../../../services/clients'
import { IntegrationTestResult } from '../../../services/healthService'
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
}) => {
  const [testResult, setTestResult] = useState<IntegrationTestResult | null>(null)

  return (
    <section className="space-y-5">
      <div className="flex flex-col gap-4 rounded-3xl border border-slate-200/70 bg-slate-50/60 p-6 backdrop-blur-sm lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white text-slate-600 ring-1 ring-slate-200">
              <Activity className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h3 className="text-xl font-semibold tracking-[0.02em] text-slate-900">系统状态监控</h3>
              <p className="mt-1.5 text-sm leading-6 text-slate-500">集中查看系统运行状态、消息变化与自检结果。</p>
            </div>
            <span className="inline-flex items-center rounded-full bg-white px-3 py-1.5 text-xs font-medium text-blue-700 ring-1 ring-blue-200">
              {messages.length} 条消息
            </span>
            {/* <button
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
            </button> */}
          </div>
        </div>
      </div>

      {/* 状态概览 */}
      {/* <div className="px-6 py-4 border-b bg-white">
        <div className="flex justify-end">
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
      </div> */}

      {/* 诊断结果 */}
      {testResult && (
        <div className="rounded-3xl border border-slate-200 bg-white/80 p-6 shadow-sm backdrop-blur-sm">
          <div className="mb-5 flex items-center justify-between">
            <h4 className="flex items-center text-base font-semibold text-slate-900">
              <Activity className="mr-2.5 h-4 w-4 text-indigo-500" />
              组件自检报告
            </h4>
            <button
              onClick={() => setTestResult(null)}
              className="rounded-xl p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div
              className={`rounded-3xl border p-5 ${
                testResult.content_model.status === 'ok' ? 'border-green-200 bg-green-50/70' : 'border-red-200 bg-red-50/70'
              }`}
            >
              <div className="flex items-start gap-3.5">
                {testResult.content_model.status === 'ok' ? (
                  <CheckCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-500" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" />
                )}
                <div>
                  <p
                    className={`text-sm font-semibold ${
                      testResult.content_model.status === 'ok' ? 'text-green-800' : 'text-red-800'
                    }`}
                  >
                    文案生成模型
                  </p>
                  <p
                    className={`mt-1.5 text-sm leading-6 ${
                      testResult.content_model.status === 'ok' ? 'text-green-700' : 'text-red-700'
                    }`}
                  >
                    {testResult.content_model.message}
                  </p>
                </div>
              </div>
            </div>

            <div
              className={`rounded-3xl border p-5 ${
                testResult.tts.status === 'ok' ? 'border-green-200 bg-green-50/70' : 'border-red-200 bg-red-50/70'
              }`}
            >
              <div className="flex items-start gap-3.5">
                {testResult.tts.status === 'ok' ? (
                  <CheckCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-500" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" />
                )}
                <div>
                  <p
                    className={`text-sm font-semibold ${
                      testResult.tts.status === 'ok' ? 'text-green-800' : 'text-red-800'
                    }`}
                  >
                    语音合成引擎 (TTS)
                  </p>
                  <p
                    className={`mt-1.5 text-sm leading-6 ${
                      testResult.tts.status === 'ok' ? 'text-green-700' : 'text-red-700'
                    }`}
                  >
                    {testResult.tts.message}
                  </p>
                </div>
              </div>
            </div>

            <div
              className={`rounded-3xl border p-5 ${
                testResult.asr.status === 'ok' ? 'border-green-200 bg-green-50/70' : 'border-red-200 bg-red-50/70'
              }`}
            >
              <div className="flex items-start gap-3.5">
                {testResult.asr.status === 'ok' ? (
                  <CheckCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-green-500" />
                ) : (
                  <AlertTriangle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" />
                )}
                <div>
                  <p
                    className={`text-sm font-semibold ${
                      testResult.asr.status === 'ok' ? 'text-green-800' : 'text-red-800'
                    }`}
                  >
                    语音识别引擎 (ASR)
                  </p>
                  <p
                    className={`mt-1.5 text-sm leading-6 ${
                      testResult.asr.status === 'ok' ? 'text-green-700' : 'text-red-700'
                    }`}
                  >
                    {testResult.asr.message}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-5">
        <LogConsolePanel enabled />
        {/* <WebSocketMessagesPanel messages={messages} /> */}
      </div>
    </section>
  )
}

export default StatusPanel
