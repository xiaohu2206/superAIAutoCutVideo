import { CheckCircle, Info, RefreshCw } from "lucide-react";
import React, { useEffect, useState } from "react";
import {
  TauriCommands,
  WebSocketMessage,
  apiClient,
  wsClient,
  configureBackend,
  autoConfigureBackend,
} from "./api/client";
import Navigation from "./components/Navigation";
import SettingsPage from "./components/settingsPage";
import StatusPanel from "./components/StatusPanel";
import VideoProcessor from "./components/VideoProcessor";
import ProjectManagementPage from "./pages/ProjectManagementPage";
import ProjectEditPage from "./pages/ProjectEditPage";

interface BackendStatus {
  running: boolean;
  port: number;
  pid?: number;
}

const App: React.FC = () => {
  // 状态管理
  const [backendStatus, setBackendStatus] = useState<BackendStatus>({
    running: false,
    port: 8000,
  });
  const [connectionStatus, setConnectionStatus] = useState({
    backend: false,
    api: false,
    websocket: false,
  });
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("home");
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);

  // 初始化应用
  useEffect(() => {
    // 设置WebSocket事件监听器
    wsClient.on("message", (message: WebSocketMessage) => {
      setMessages((prev) => [...prev, message]);
    });

    wsClient.on("open", () => {
      console.log("WebSocket连接状态更新: 已连接");
      setConnectionStatus((prev) => ({ ...prev, websocket: true }));
    });

    wsClient.on("close", () => {
      console.log("WebSocket连接状态更新: 已断开");
      setConnectionStatus((prev) => ({ ...prev, websocket: false }));
    });

    wsClient.on("error", (error) => {
      console.error("WebSocket连接错误:", error);
      setConnectionStatus((prev) => ({ ...prev, websocket: false }));
    });

    // 初始化应用
    initializeApp();

    return () => {
      wsClient.disconnect();
    };
  }, []);

  const initializeApp = async () => {
    try {
      setIsLoading(true);

      // 并行检查后端状态和测试API连接，提高速度
      const [status] = await Promise.allSettled([
        checkBackendStatus(),
        testApiConnection(),
      ]);

      // 获取后端状态结果
      const backendStatus = status.status === "fulfilled" ? status.value : null;

      // 尝试连接WebSocket（仅在后端运行时）
      if (backendStatus && backendStatus.running) {
        console.log("后端正在运行，尝试连接WebSocket...");
        // 设置WebSocket连接超时，避免长时间等待
        const wsTimeout = new Promise((_, reject) =>
          setTimeout(() => reject(new Error("WebSocket连接超时")), 2000)
        );

        try {
          await Promise.race([wsClient.connect(), wsTimeout]);
          console.log("WebSocket连接成功");
        } catch (error) {
          console.error("WebSocket连接失败:", error);
          // 不阻塞初始化流程
        }
      } else {
        console.log("后端未运行，跳过WebSocket连接");
      }
    } catch (error) {
      console.error("初始化应用失败:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const checkBackendStatus = async (): Promise<BackendStatus | null> => {
    try {
      let status: BackendStatus;
      // 检查是否在Tauri环境中
      if (typeof (window as any).__TAURI_IPC__ === "function") {
        status = await TauriCommands.getBackendStatus();
        // 根据返回端口动态配置 API 与 WS 端点
        if (status?.port) {
          configureBackend(status.port);
        }
      } else {
        // 在浏览器环境中，尝试自动发现后端端口
        console.log("浏览器环境，尝试自动发现后端端口...");
        const discovered = await autoConfigureBackend();
        if (discovered) {
          // 获取实际配置的端口信息（添加超时）
          try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 1000);

            const serverInfo = await fetch(
              `${apiClient.getBaseUrl()}/api/server/info`,
              {
                method: "GET",
                headers: { "Content-Type": "application/json" },
                signal: controller.signal,
              }
            ).then((res) => res.json());

            clearTimeout(timeoutId);

            if (serverInfo.data && serverInfo.data.port) {
              status = { running: true, port: serverInfo.data.port };
            } else {
              status = { running: true, port: 8000 };
            }
          } catch (error) {
            console.warn("获取服务器信息失败，使用默认端口:", error);
            status = { running: true, port: 8000 };
          }
        } else {
          console.warn("无法发现后端服务，使用默认配置");
          status = { running: false, port: 8000 };
        }
      }
      setBackendStatus(status);
      setConnectionStatus((prev) => ({ ...prev, backend: status.running }));
      return status;
    } catch (error) {
      console.error("检查后端状态失败:", error);
      setConnectionStatus((prev) => ({ ...prev, backend: false }));
      return null;
    }
  };

  const testApiConnection = async () => {
    try {
      const response = await apiClient.testConnection();
      setConnectionStatus((prev) => ({ ...prev, api: response }));
    } catch (error) {
      setConnectionStatus((prev) => ({ ...prev, api: false }));
    }
  };

  const handleStartBackend = async () => {
    try {
      const result = await TauriCommands.startBackend();
      if (result.running) {
        const status = await checkBackendStatus();
        await testApiConnection();
        if (status && status.running) {
          try {
            await wsClient.connect();
          } catch (error) {
            console.error("WebSocket连接失败:", error);
          }
        }
        await TauriCommands.showNotification("后端服务已启动", "success");
      }
    } catch (error) {
      console.error("启动后端失败:", error);
      await TauriCommands.showNotification("启动后端失败", "error");
    }
  };

  const handleStopBackend = async () => {
    try {
      wsClient.disconnect();
      const result = await TauriCommands.stopBackend();
      if (result) {
        await checkBackendStatus();
        setConnectionStatus({ backend: false, api: false, websocket: false });
        await TauriCommands.showNotification("后端服务已停止", "info");
      }
    } catch (error) {
      console.error("停止后端失败:", error);
      await TauriCommands.showNotification("停止后端失败", "error");
    }
  };

  const handleApiCall = async () => {
    try {
      const response = await apiClient.get("/api/status");
      await TauriCommands.showNotification(
        `API调用成功: ${JSON.stringify(response)}`,
        "success"
      );
    } catch (error) {
      console.error("API调用失败:", error);
      await TauriCommands.showNotification("API调用失败", "error");
    }
  };

  const handleWebSocketToggle = async () => {
    if (connectionStatus.websocket) {
      console.log("断开WebSocket连接...");
      wsClient.disconnect();
    } else {
      console.log("尝试连接WebSocket...");
      try {
        await wsClient.connect();
        console.log("WebSocket连接成功");
      } catch (error) {
        console.error("WebSocket连接失败:", error);
        // 可以在这里显示错误通知
        if (typeof (window as any).__TAURI_IPC__ === "function") {
          await TauriCommands.showNotification("WebSocket连接失败", "error");
        }
      }
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="h-8 w-8 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-gray-600">正在初始化应用...</p>
        </div>
      </div>
    );
  }

  const renderAboutContent = () => (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex items-center mb-6">
          <Info className="h-6 w-6 text-blue-600 mr-3" />
          <h2 className="text-2xl font-bold text-gray-900">关于应用</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <h3 className="text-lg font-medium text-gray-900 mb-3">应用信息</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-600">应用名称:</dt>
                <dd className="font-medium">AI智能视频剪辑</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-600">版本:</dt>
                <dd className="font-medium">1.0.0</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-600">构建时间:</dt>
                <dd className="font-medium">
                  {new Date().toLocaleDateString("zh-CN")}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-gray-600">开发者:</dt>
                <dd className="font-medium">SuperAutoCutVideo Team</dd>
              </div>
            </dl>
          </div>

          <div>
            <h3 className="text-lg font-medium text-gray-900 mb-3">技术栈</h3>
            <div className="space-y-2 text-sm">
              <div className="flex items-center">
                <div className="w-2 h-2 bg-blue-500 rounded-full mr-2" />
                <span>React 18 + TypeScript</span>
              </div>
              <div className="flex items-center">
                <div className="w-2 h-2 bg-green-500 rounded-full mr-2" />
                <span>Tauri (Rust)</span>
              </div>
              <div className="flex items-center">
                <div className="w-2 h-2 bg-yellow-500 rounded-full mr-2" />
                <span>Python FastAPI</span>
              </div>
              <div className="flex items-center">
                <div className="w-2 h-2 bg-purple-500 rounded-full mr-2" />
                <span>TailwindCSS</span>
              </div>
              <div className="flex items-center">
                <div className="w-2 h-2 bg-red-500 rounded-full mr-2" />
                <span>OpenCV + FFmpeg</span>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-6 pt-6 border-t border-gray-200">
          <h3 className="text-lg font-medium text-gray-900 mb-3">功能特性</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <ul className="space-y-2">
              <li className="flex items-center">
                <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
                <span>跨平台桌面应用</span>
              </li>
              <li className="flex items-center">
                <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
                <span>实时视频处理</span>
              </li>
              <li className="flex items-center">
                <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
                <span>WebSocket实时通信</span>
              </li>
            </ul>
            <ul className="space-y-2">
              <li className="flex items-center">
                <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
                <span>现代化UI界面</span>
              </li>
              <li className="flex items-center">
                <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
                <span>智能场景检测</span>
              </li>
              <li className="flex items-center">
                <CheckCircle className="h-4 w-4 text-green-500 mr-2" />
                <span>多格式支持</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 导航栏 */}
      <Navigation activeTab={activeTab} onTabChange={setActiveTab} />

      {/* 主要内容区域 */}
      <main className="max-w-7xl mx-auto py-6 px-4 sm:px-6 lg:px-8">
        {/* 标签页内容 */}
        {activeTab === "home" && !currentProjectId && (
          <ProjectManagementPage
            onEditProject={(projectId) => setCurrentProjectId(projectId)}
          />
        )}

        {activeTab === "home" && currentProjectId && (
          <ProjectEditPage
            projectId={currentProjectId}
            onBack={() => setCurrentProjectId(null)}
          />
        )}

        {activeTab === "video" && <VideoProcessor />}

        {activeTab === "monitor" && (
          <StatusPanel
            messages={messages}
            backendStatus={backendStatus}
            connections={connectionStatus}
          />
        )}

        {activeTab === "settings" && <SettingsPage />}

        {activeTab === "about" && renderAboutContent()}
      </main>
    </div>
  );
};

export default App;
