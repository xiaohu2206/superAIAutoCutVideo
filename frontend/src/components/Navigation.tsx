import React from 'react'
import { 
  Home, 
  Video, 
  Settings, 
  Activity, 
  Info,
  Github,
  ExternalLink
} from 'lucide-react'

interface NavigationProps {
  activeTab: string
  onTabChange: (tab: string) => void
  className?: string
}

const Navigation: React.FC<NavigationProps> = ({ 
  activeTab, 
  onTabChange, 
  className = '' 
}) => {
  const navItems = [
    {
      id: 'home',
      label: '首页',
      icon: Home,
      description: '应用概览和快速操作'
    },
    {
      id: 'video',
      label: '视频处理',
      icon: Video,
      description: '上传和处理视频文件'
    },
    {
      id: 'monitor',
      label: '系统监控',
      icon: Activity,
      description: '查看系统状态和日志'
    },
    {
      id: 'settings',
      label: '设置',
      icon: Settings,
      description: '应用配置和偏好设置'
    },
    {
      id: 'about',
      label: '关于',
      icon: Info,
      description: '应用信息和帮助'
    }
  ]

  return (
    <nav className={`bg-white shadow-sm border-b ${className}`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo和标题 */}
          <div className="flex items-center space-x-3">
            <div className="flex items-center justify-center w-10 h-10 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg">
              <Video className="h-6 w-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">AI智能视频剪辑</h1>
              <p className="text-xs text-gray-500">SuperAutoCutVideo</p>
            </div>
          </div>

          {/* 导航菜单 */}
          <div className="hidden md:flex items-center space-x-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = activeTab === item.id
              
              return (
                <button
                  key={item.id}
                  onClick={() => onTabChange(item.id)}
                  className={`
                    flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200
                    ${isActive 
                      ? 'bg-blue-100 text-blue-700 shadow-sm' 
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                    }
                  `}
                  title={item.description}
                >
                  <Icon className={`h-4 w-4 mr-2 ${isActive ? 'text-blue-600' : 'text-gray-500'}`} />
                  {item.label}
                </button>
              )
            })}
          </div>

          {/* 右侧操作 */}
          <div className="flex items-center space-x-3">
            {/* GitHub链接 */}
            <button
              onClick={() => window.open('https://github.com', '_blank')}
              className="p-2 text-gray-500 hover:text-gray-700 transition-colors"
              title="查看源代码"
            >
              <Github className="h-5 w-5" />
            </button>

            {/* 帮助链接 */}
            <button
              onClick={() => window.open('https://docs.example.com', '_blank')}
              className="p-2 text-gray-500 hover:text-gray-700 transition-colors"
              title="查看文档"
            >
              <ExternalLink className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* 移动端导航 */}
        <div className="md:hidden border-t border-gray-200">
          <div className="flex overflow-x-auto py-2 space-x-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = activeTab === item.id
              
              return (
                <button
                  key={item.id}
                  onClick={() => onTabChange(item.id)}
                  className={`
                    flex flex-col items-center px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200 min-w-0 flex-shrink-0
                    ${isActive 
                      ? 'bg-blue-100 text-blue-700' 
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                    }
                  `}
                >
                  <Icon className={`h-4 w-4 mb-1 ${isActive ? 'text-blue-600' : 'text-gray-500'}`} />
                  <span className="truncate">{item.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </nav>
  )
}

export default Navigation