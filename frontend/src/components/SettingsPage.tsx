import {
  Folder,
  Info,
  Monitor,
  Palette,
  RotateCcw,
  Save,
  Server,
  Settings,
  Shield
} from 'lucide-react'
import React, { useEffect, useState } from 'react'
import { TauriCommands } from '../api/client'

interface AppSettings {
  // 后端设置
  backend: {
    autoStart: boolean
    port: number
    timeout: number
    maxRetries: number
  }
  
  // 文件路径设置
  paths: {
    defaultInputDir: string
    defaultOutputDir: string
    tempDir: string
  }
  
  // 界面设置
  ui: {
    theme: 'light' | 'dark' | 'auto'
    language: 'zh-CN' | 'en-US'
    showNotifications: boolean
    autoSaveSettings: boolean
  }
  
  // 视频处理设置
  video: {
    defaultFormat: string
    defaultQuality: string
    maxFileSize: number // MB
    enableHardwareAcceleration: boolean
  }
  
  // 高级设置
  advanced: {
    enableDebugMode: boolean
    logLevel: 'error' | 'warn' | 'info' | 'debug'
    maxLogFiles: number
    enableTelemetry: boolean
  }
}

const defaultSettings: AppSettings = {
  backend: {
    autoStart: true,
    port: 8000,
    timeout: 30,
    maxRetries: 3
  },
  paths: {
    defaultInputDir: '',
    defaultOutputDir: '',
    tempDir: ''
  },
  ui: {
    theme: 'auto',
    language: 'zh-CN',
    showNotifications: true,
    autoSaveSettings: true
  },
  video: {
    defaultFormat: 'mp4',
    defaultQuality: 'high',
    maxFileSize: 1024, // 1GB
    enableHardwareAcceleration: true
  },
  advanced: {
    enableDebugMode: false,
    logLevel: 'info',
    maxLogFiles: 10,
    enableTelemetry: false
  }
}

const SettingsPage: React.FC = () => {
  const [settings, setSettings] = useState<AppSettings>(defaultSettings)
  const [hasChanges, setHasChanges] = useState(false)
  const [activeSection, setActiveSection] = useState('backend')
  const [isSaving, setIsSaving] = useState(false)

  // 加载设置
  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    try {
      // 从本地存储或配置文件加载设置
      const savedSettings = localStorage.getItem('app-settings')
      if (savedSettings) {
        setSettings({ ...defaultSettings, ...JSON.parse(savedSettings) })
      }
    } catch (error) {
      console.error('加载设置失败:', error)
    }
  }

  const saveSettings = async () => {
    try {
      setIsSaving(true)
      
      // 保存到本地存储
      localStorage.setItem('app-settings', JSON.stringify(settings))
      
      // 显示成功通知
      await TauriCommands.showNotification('成功', '设置已保存')
      setHasChanges(false)
    } catch (error) {
      console.error('保存设置失败:', error)
      await TauriCommands.showNotification('错误', '保存设置失败')
    } finally {
      setIsSaving(false)
    }
  }

  const resetSettings = async () => {
    if (confirm('确定要重置所有设置吗？此操作不可撤销。')) {
      setSettings(defaultSettings)
      setHasChanges(true)
      await TauriCommands.showNotification('信息', '设置已重置')
    }
  }

  const updateSetting = (path: string, value: any) => {
    setSettings(prev => {
      const newSettings = { ...prev }
      const keys = path.split('.')
      let current: any = newSettings
      
      for (let i = 0; i < keys.length - 1; i++) {
        current = current[keys[i]]
      }
      
      current[keys[keys.length - 1]] = value
      return newSettings
    })
    setHasChanges(true)
  }

  const selectDirectory = async (settingPath: string) => {
    try {
      // 检查是否在Tauri环境中
       if (typeof (window as any).__TAURI_IPC__ === 'function') {
        const result = await TauriCommands.selectOutputDirectory()
        if (!result.cancelled && result.path) {
          updateSetting(settingPath, result.path)
        }
      } else {
        // 在浏览器环境中，使用默认路径
        updateSetting(settingPath, '/default/path')
      }
    } catch (error) {
      console.error('选择目录失败:', error)
    }
  }

  const sections = [
    { id: 'backend', label: '后端设置', icon: Server },
    { id: 'paths', label: '路径设置', icon: Folder },
    { id: 'ui', label: '界面设置', icon: Palette },
    { id: 'video', label: '视频设置', icon: Monitor },
    { id: 'advanced', label: '高级设置', icon: Shield }
  ]

  const renderBackendSettings = () => (
    <div className="space-y-6">
      <div>
        <label className="flex items-center">
          <input
            type="checkbox"
            checked={settings.backend.autoStart}
            onChange={(e) => updateSetting('backend.autoStart', e.target.checked)}
            className="mr-3"
          />
          <span className="text-sm font-medium text-gray-700">应用启动时自动启动后端服务</span>
        </label>
        <p className="text-xs text-gray-500 mt-1">启用后，应用启动时会自动启动Python后端服务</p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          后端端口
        </label>
        <input
          type="number"
          min="1000"
          max="65535"
          value={settings.backend.port}
          onChange={(e) => updateSetting('backend.port', Number(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">后端服务监听的端口号 (1000-65535)</p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          连接超时 (秒)
        </label>
        <input
          type="number"
          min="5"
          max="300"
          value={settings.backend.timeout}
          onChange={(e) => updateSetting('backend.timeout', Number(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">连接后端服务的超时时间</p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          最大重试次数
        </label>
        <input
          type="number"
          min="0"
          max="10"
          value={settings.backend.maxRetries}
          onChange={(e) => updateSetting('backend.maxRetries', Number(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">连接失败时的最大重试次数</p>
      </div>
    </div>
  )

  const renderPathSettings = () => (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          默认输入目录
        </label>
        <div className="flex space-x-2">
          <input
            type="text"
            value={settings.paths.defaultInputDir}
            onChange={(e) => updateSetting('paths.defaultInputDir', e.target.value)}
            placeholder="选择默认的视频输入目录"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={() => selectDirectory('paths.defaultInputDir')}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
          >
            <Folder className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          默认输出目录
        </label>
        <div className="flex space-x-2">
          <input
            type="text"
            value={settings.paths.defaultOutputDir}
            onChange={(e) => updateSetting('paths.defaultOutputDir', e.target.value)}
            placeholder="选择默认的视频输出目录"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={() => selectDirectory('paths.defaultOutputDir')}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
          >
            <Folder className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          临时文件目录
        </label>
        <div className="flex space-x-2">
          <input
            type="text"
            value={settings.paths.tempDir}
            onChange={(e) => updateSetting('paths.tempDir', e.target.value)}
            placeholder="选择临时文件存储目录"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={() => selectDirectory('paths.tempDir')}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
          >
            <Folder className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )

  const renderUISettings = () => (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          主题
        </label>
        <select
          value={settings.ui.theme}
          onChange={(e) => updateSetting('ui.theme', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="light">浅色主题</option>
          <option value="dark">深色主题</option>
          <option value="auto">跟随系统</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          语言
        </label>
        <select
          value={settings.ui.language}
          onChange={(e) => updateSetting('ui.language', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="zh-CN">简体中文</option>
          <option value="en-US">English</option>
        </select>
      </div>

      <div>
        <label className="flex items-center">
          <input
            type="checkbox"
            checked={settings.ui.showNotifications}
            onChange={(e) => updateSetting('ui.showNotifications', e.target.checked)}
            className="mr-3"
          />
          <span className="text-sm font-medium text-gray-700">显示系统通知</span>
        </label>
      </div>

      <div>
        <label className="flex items-center">
          <input
            type="checkbox"
            checked={settings.ui.autoSaveSettings}
            onChange={(e) => updateSetting('ui.autoSaveSettings', e.target.checked)}
            className="mr-3"
          />
          <span className="text-sm font-medium text-gray-700">自动保存设置</span>
        </label>
      </div>
    </div>
  )

  const renderVideoSettings = () => (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          默认输出格式
        </label>
        <select
          value={settings.video.defaultFormat}
          onChange={(e) => updateSetting('video.defaultFormat', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="mp4">MP4</option>
          <option value="avi">AVI</option>
          <option value="mov">MOV</option>
          <option value="mkv">MKV</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          默认输出质量
        </label>
        <select
          value={settings.video.defaultQuality}
          onChange={(e) => updateSetting('video.defaultQuality', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="low">低质量</option>
          <option value="medium">中等质量</option>
          <option value="high">高质量</option>
          <option value="ultra">超高质量</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          最大文件大小 (MB)
        </label>
        <input
          type="number"
          min="100"
          max="10240"
          value={settings.video.maxFileSize}
          onChange={(e) => updateSetting('video.maxFileSize', Number(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">允许处理的最大视频文件大小</p>
      </div>

      <div>
        <label className="flex items-center">
          <input
            type="checkbox"
            checked={settings.video.enableHardwareAcceleration}
            onChange={(e) => updateSetting('video.enableHardwareAcceleration', e.target.checked)}
            className="mr-3"
          />
          <span className="text-sm font-medium text-gray-700">启用硬件加速</span>
        </label>
        <p className="text-xs text-gray-500 mt-1">使用GPU加速视频处理 (需要支持的硬件)</p>
      </div>
    </div>
  )

  const renderAdvancedSettings = () => (
    <div className="space-y-6">
      <div>
        <label className="flex items-center">
          <input
            type="checkbox"
            checked={settings.advanced.enableDebugMode}
            onChange={(e) => updateSetting('advanced.enableDebugMode', e.target.checked)}
            className="mr-3"
          />
          <span className="text-sm font-medium text-gray-700">启用调试模式</span>
        </label>
        <p className="text-xs text-gray-500 mt-1">显示详细的调试信息和日志</p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          日志级别
        </label>
        <select
          value={settings.advanced.logLevel}
          onChange={(e) => updateSetting('advanced.logLevel', e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="error">错误</option>
          <option value="warn">警告</option>
          <option value="info">信息</option>
          <option value="debug">调试</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          最大日志文件数
        </label>
        <input
          type="number"
          min="1"
          max="100"
          value={settings.advanced.maxLogFiles}
          onChange={(e) => updateSetting('advanced.maxLogFiles', Number(e.target.value))}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <div>
        <label className="flex items-center">
          <input
            type="checkbox"
            checked={settings.advanced.enableTelemetry}
            onChange={(e) => updateSetting('advanced.enableTelemetry', e.target.checked)}
            className="mr-3"
          />
          <span className="text-sm font-medium text-gray-700">启用遥测数据收集</span>
        </label>
        <p className="text-xs text-gray-500 mt-1">帮助改进应用性能和稳定性</p>
      </div>
    </div>
  )

  const renderSectionContent = () => {
    switch (activeSection) {
      case 'backend':
        return renderBackendSettings()
      case 'paths':
        return renderPathSettings()
      case 'ui':
        return renderUISettings()
      case 'video':
        return renderVideoSettings()
      case 'advanced':
        return renderAdvancedSettings()
      default:
        return null
    }
  }

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="bg-white rounded-lg shadow-md overflow-hidden">
        {/* 头部 */}
        <div className="px-6 py-4 bg-gray-50 border-b">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Settings className="h-6 w-6 text-gray-600" />
              <h2 className="text-xl font-semibold text-gray-900">应用设置</h2>
            </div>
            
            <div className="flex items-center space-x-3">
              {hasChanges && (
                <span className="text-sm text-orange-600 flex items-center">
                  <Info className="h-4 w-4 mr-1" />
                  有未保存的更改
                </span>
              )}
              
              <button
                onClick={resetSettings}
                className="flex items-center px-3 py-2 text-sm text-gray-600 hover:text-gray-800 transition-colors"
              >
                <RotateCcw className="h-4 w-4 mr-1" />
                重置
              </button>
              
              <button
                onClick={saveSettings}
                disabled={!hasChanges || isSaving}
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Save className="h-4 w-4 mr-2" />
                {isSaving ? '保存中...' : '保存设置'}
              </button>
            </div>
          </div>
        </div>

        <div className="flex">
          {/* 侧边栏 */}
          <div className="w-64 bg-gray-50 border-r">
            <nav className="p-4 space-y-1">
              {sections.map((section) => {
                const Icon = section.icon
                const isActive = activeSection === section.id
                
                return (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={`
                      w-full flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-colors
                      ${isActive 
                        ? 'bg-blue-100 text-blue-700' 
                        : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                      }
                    `}
                  >
                    <Icon className={`h-4 w-4 mr-3 ${isActive ? 'text-blue-600' : 'text-gray-500'}`} />
                    {section.label}
                  </button>
                )
              })}
            </nav>
          </div>

          {/* 主内容区 */}
          <div className="flex-1 p-6">
            <div className="max-w-2xl">
              <h3 className="text-lg font-medium text-gray-900 mb-6">
                {sections.find(s => s.id === activeSection)?.label}
              </h3>
              
              {renderSectionContent()}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default SettingsPage