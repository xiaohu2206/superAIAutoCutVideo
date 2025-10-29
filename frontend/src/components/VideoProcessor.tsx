import {
  AlertCircle,
  CheckCircle,
  Clock,
  Download,
  FileVideo,
  Pause,
  Scissors,
  Settings,
  Upload,
  X,
  Zap
} from 'lucide-react'
import React, { useCallback, useRef, useState } from 'react'
import { TauriCommands, apiClient } from '../api/client'

interface VideoFile {
  name: string
  path: string
  size: number
  duration?: number
  format?: string
}

interface ProcessingParams {
  outputFormat: string
  quality: string
  startTime: number
  endTime: number
  autoDetectScenes: boolean
  compressionLevel: number
  removeAudio: boolean
}

interface ProcessingTask {
  id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  progress: number
  message: string
  outputPath?: string
  startTime: Date
  endTime?: Date
}

const VideoProcessor: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<VideoFile | null>(null)
  const [processingParams, setProcessingParams] = useState<ProcessingParams>({
    outputFormat: 'mp4',
    quality: 'high',
    startTime: 0,
    endTime: 0,
    autoDetectScenes: true,
    compressionLevel: 50,
    removeAudio: false
  })
  const [currentTask, setCurrentTask] = useState<ProcessingTask | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 选择视频文件
  const handleFileSelect = useCallback(async () => {
    try {
      // 检查是否在Tauri环境中
      if (typeof (window as any).__TAURI_IPC__ !== 'function') {
        // 在浏览器环境中，使用文件输入
        fileInputRef.current?.click()
        return
      }
      
      const result = await TauriCommands.selectVideoFile()
      if (!result.cancelled && result.path) {
        // 获取文件信息
        const fileInfo = await apiClient.getVideoInfo(result.path)
        
        setSelectedFile({
          name: result.path.split(/[/\\]/).pop() || 'unknown',
          path: result.path,
          size: 0, // 文件大小需要从其他地方获取
          duration: fileInfo.duration,
          format: fileInfo.format
        })

        // 设置默认结束时间为视频总时长
        if (fileInfo.duration) {
          setProcessingParams(prev => ({
            ...prev,
            endTime: fileInfo.duration || 0
          }))
        }
      }
    } catch (error) {
      console.error('选择文件失败:', error)
      await TauriCommands.showNotification('错误', '选择文件失败')
    }
  }, [])

  // 开始处理视频
  const handleStartProcessing = useCallback(async () => {
    if (!selectedFile) {
      await TauriCommands.showNotification('警告', '请先选择视频文件')
      return
    }

    try {
      setIsProcessing(true)
      
      // 选择输出目录
      let outputPath = ''
      if (typeof (window as any).__TAURI_IPC__ === 'function') {
        const outputDir = await TauriCommands.selectOutputDirectory()
        if (outputDir.cancelled || !outputDir.path) {
          setIsProcessing(false)
          return
        }
        outputPath = outputDir.path
      } else {
        // 在浏览器环境中，使用默认输出路径
        outputPath = '/default/output'
      }

      // 创建处理任务
      const taskId = `task_${Date.now()}`
      const task: ProcessingTask = {
        id: taskId,
        status: 'pending',
        progress: 0,
        message: '准备开始处理...',
        startTime: new Date()
      }
      setCurrentTask(task)

      // 调用后端API开始处理
      const response = await apiClient.processVideo({
        video_path: selectedFile.path,
        output_path: outputPath,
        settings: {
          format: processingParams.outputFormat,
          quality: processingParams.quality,
          start_time: processingParams.startTime,
          end_time: processingParams.endTime,
          auto_detect_scenes: processingParams.autoDetectScenes,
          compression_level: processingParams.compressionLevel,
          remove_audio: processingParams.removeAudio
        }
      })

      if (response.task_id) {
        setCurrentTask(prev => prev ? {
          ...prev,
          status: 'processing',
          message: '正在处理视频...'
        } : null)
        
        await TauriCommands.showNotification('成功', '视频处理已开始')
      } else {
        throw new Error('启动处理失败')
      }
    } catch (error) {
      console.error('处理视频失败:', error)
      setCurrentTask(prev => prev ? {
        ...prev,
        status: 'failed',
        message: `处理失败: ${error instanceof Error ? error.message : '未知错误'}`,
        endTime: new Date()
      } : null)
      await TauriCommands.showNotification('错误', '视频处理失败')
    } finally {
      setIsProcessing(false)
    }
  }, [selectedFile, processingParams])

  // 取消处理
  const handleCancelProcessing = useCallback(() => {
    if (currentTask && currentTask.status === 'processing') {
      setCurrentTask(prev => prev ? {
        ...prev,
        status: 'failed',
        message: '用户取消处理',
        endTime: new Date()
      } : null)
      setIsProcessing(false)
    }
  }, [currentTask])

  // 下载处理结果
  const handleDownload = useCallback(async () => {
    if (currentTask?.outputPath) {
      try {
        await TauriCommands.openExternalLink(currentTask.outputPath)
      } catch (error) {
        console.error('打开文件失败:', error)
        await TauriCommands.showNotification('错误', '打开文件失败')
      }
    }
  }, [currentTask])

  // 格式化文件大小
  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  // 格式化时间
  const formatDuration = (seconds: number): string => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = Math.floor(seconds % 60)
    
    if (hours > 0) {
      return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
    }
    return `${minutes}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="space-y-6">
      {/* 文件选择区域 */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
          <FileVideo className="h-5 w-5 mr-2" />
          视频文件选择
        </h3>
        
        {!selectedFile ? (
          <div 
            className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-gray-400 transition-colors cursor-pointer"
            onClick={handleFileSelect}
          >
            <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-lg text-gray-600 mb-2">点击选择视频文件</p>
            <p className="text-sm text-gray-500">支持 MP4, AVI, MOV, MKV 等格式</p>
          </div>
        ) : (
          <div className="bg-gray-50 rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-3">
                <FileVideo className="h-8 w-8 text-blue-500" />
                <div>
                  <p className="font-medium text-gray-900">{selectedFile.name}</p>
                  <p className="text-sm text-gray-500">
                    {formatFileSize(selectedFile.size)}
                    {selectedFile.duration && ` • ${formatDuration(selectedFile.duration)}`}
                    {selectedFile.format && ` • ${selectedFile.format.toUpperCase()}`}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedFile(null)}
                className="p-1 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            
            <button
              onClick={handleFileSelect}
              className="text-sm text-blue-600 hover:text-blue-800 transition-colors"
            >
              重新选择文件
            </button>
          </div>
        )}
      </div>

      {/* 处理参数设置 */}
      {selectedFile && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900 flex items-center">
              <Settings className="h-5 w-5 mr-2" />
              处理参数
            </h3>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="text-sm text-blue-600 hover:text-blue-800 transition-colors"
            >
              {showSettings ? '收起设置' : '展开设置'}
            </button>
          </div>

          {showSettings && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* 输出格式 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  输出格式
                </label>
                <select
                  value={processingParams.outputFormat}
                  onChange={(e) => setProcessingParams(prev => ({ ...prev, outputFormat: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="mp4">MP4</option>
                  <option value="avi">AVI</option>
                  <option value="mov">MOV</option>
                  <option value="mkv">MKV</option>
                </select>
              </div>

              {/* 质量设置 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  输出质量
                </label>
                <select
                  value={processingParams.quality}
                  onChange={(e) => setProcessingParams(prev => ({ ...prev, quality: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="low">低质量 (快速)</option>
                  <option value="medium">中等质量</option>
                  <option value="high">高质量</option>
                  <option value="ultra">超高质量 (慢速)</option>
                </select>
              </div>

              {/* 时间范围 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  开始时间 (秒)
                </label>
                <input
                  type="number"
                  min="0"
                  max={selectedFile.duration || 0}
                  value={processingParams.startTime}
                  onChange={(e) => setProcessingParams(prev => ({ ...prev, startTime: Number(e.target.value) }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  结束时间 (秒)
                </label>
                <input
                  type="number"
                  min={processingParams.startTime}
                  max={selectedFile.duration || 0}
                  value={processingParams.endTime}
                  onChange={(e) => setProcessingParams(prev => ({ ...prev, endTime: Number(e.target.value) }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* 压缩级别 */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  压缩级别: {processingParams.compressionLevel}%
                </label>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={processingParams.compressionLevel}
                  onChange={(e) => setProcessingParams(prev => ({ ...prev, compressionLevel: Number(e.target.value) }))}
                  className="w-full"
                />
              </div>

              {/* 其他选项 */}
              <div className="space-y-3">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={processingParams.autoDetectScenes}
                    onChange={(e) => setProcessingParams(prev => ({ ...prev, autoDetectScenes: e.target.checked }))}
                    className="mr-2"
                  />
                  <span className="text-sm text-gray-700">自动检测场景切换</span>
                </label>
                
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={processingParams.removeAudio}
                    onChange={(e) => setProcessingParams(prev => ({ ...prev, removeAudio: e.target.checked }))}
                    className="mr-2"
                  />
                  <span className="text-sm text-gray-700">移除音频</span>
                </label>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 处理控制 */}
      {selectedFile && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
            <Scissors className="h-5 w-5 mr-2" />
            视频处理
          </h3>

          <div className="flex items-center space-x-4">
            {!currentTask || currentTask.status === 'completed' || currentTask.status === 'failed' ? (
              <button
                onClick={handleStartProcessing}
                disabled={isProcessing}
                className="flex items-center px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Zap className="h-5 w-5 mr-2" />
                {isProcessing ? '准备中...' : '开始处理'}
              </button>
            ) : (
              <button
                onClick={handleCancelProcessing}
                className="flex items-center px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
              >
                <Pause className="h-5 w-5 mr-2" />
                取消处理
              </button>
            )}

            {currentTask?.status === 'completed' && currentTask.outputPath && (
              <button
                onClick={handleDownload}
                className="flex items-center px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
              >
                <Download className="h-5 w-5 mr-2" />
                打开结果
              </button>
            )}
          </div>
        </div>
      )}

      {/* 处理进度 */}
      {currentTask && (
        <div className="bg-white rounded-lg shadow-md p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4 flex items-center">
            <Clock className="h-5 w-5 mr-2" />
            处理进度
          </h3>

          <div className="space-y-4">
            {/* 状态指示器 */}
            <div className="flex items-center space-x-3">
              {currentTask.status === 'pending' && (
                <div className="h-3 w-3 bg-yellow-500 rounded-full animate-pulse" />
              )}
              {currentTask.status === 'processing' && (
                <div className="h-3 w-3 bg-blue-500 rounded-full animate-pulse" />
              )}
              {currentTask.status === 'completed' && (
                <CheckCircle className="h-5 w-5 text-green-500" />
              )}
              {currentTask.status === 'failed' && (
                <AlertCircle className="h-5 w-5 text-red-500" />
              )}
              
              <span className="text-sm font-medium text-gray-900">
                {currentTask.status === 'pending' && '等待处理'}
                {currentTask.status === 'processing' && '正在处理'}
                {currentTask.status === 'completed' && '处理完成'}
                {currentTask.status === 'failed' && '处理失败'}
              </span>
            </div>

            {/* 进度条 */}
            {currentTask.status === 'processing' && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-gray-600">
                  <span>进度</span>
                  <span>{currentTask.progress}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${currentTask.progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* 消息 */}
            <p className="text-sm text-gray-600">{currentTask.message}</p>

            {/* 时间信息 */}
            <div className="text-xs text-gray-500 space-y-1">
              <p>开始时间: {currentTask.startTime.toLocaleString('zh-CN')}</p>
              {currentTask.endTime && (
                <p>结束时间: {currentTask.endTime.toLocaleString('zh-CN')}</p>
              )}
              {currentTask.endTime && (
                <p>
                  耗时: {Math.round((currentTask.endTime.getTime() - currentTask.startTime.getTime()) / 1000)} 秒
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default VideoProcessor