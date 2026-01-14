import { RefreshCw } from "lucide-react";
import React, { useEffect, useState } from "react";
import Navigation from "./components/Navigation";
import MessageHost from "./components/ui/MessageHost";
import SettingsPage from "./components/settingsPage";
import ProjectEditPage from "./pages/ProjectEditPage";
import ProjectManagementPage from "./pages/ProjectManagementPage";
import {
  TauriCommands,
  WebSocketMessage,
  apiClient,
  autoConfigureBackend,
  configureBackend,
  wsClient,
} from "./services/clients";

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
    const handleWsMessage = (message: WebSocketMessage) => {
      setMessages((prev) => [...prev, message]);
    };
    const handleWsOpen = () => {
      console.log("WebSocket连接状态更新: 已连接");
      setConnectionStatus((prev) => ({ ...prev, websocket: true }));
    };
    const handleWsClose = () => {
      console.log("WebSocket连接状态更新: 已断开");
      setConnectionStatus((prev) => ({ ...prev, websocket: false }));
    };
    const handleWsError = (error: any) => {
      console.error("WebSocket连接错误:", error);
      setConnectionStatus((prev) => ({ ...prev, websocket: false }));
    };

    wsClient.on("*", handleWsMessage);
    wsClient.on("open", handleWsOpen);
    wsClient.on("close", handleWsClose);
    wsClient.on("error", handleWsError);

    initializeApp();

    return () => {
      wsClient.off("*", handleWsMessage);
      wsClient.off("open", handleWsOpen);
      wsClient.off("close", handleWsClose);
      wsClient.off("error", handleWsError);
      wsClient.disconnect();
    };
  }, []);

  const initializeApp = async () => {
    try {
      setIsLoading(true);

      const status = await checkBackendStatus();
      await testApiConnection();

      if (status && status.running) {
        console.log("后端正在运行，尝试连接WebSocket...");
        const wsTimeout = new Promise((_, reject) =>
          setTimeout(() => reject(new Error("WebSocket连接超时")), 2000)
        );
        try {
          await Promise.race([wsClient.connect(), wsTimeout]);
          console.log("WebSocket连接成功");
        } catch (error) {
          console.error("WebSocket连接失败:", error);
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

  const refreshConnections = async () => {
    try {
      const status = await checkBackendStatus();
      await testApiConnection();
      if (status && status.running) {
        try {
          if (!wsClient.isConnected) {
            const wsTimeout = new Promise((_, reject) =>
              setTimeout(() => reject(new Error("WebSocket连接超时")), 1000)
            );
            await Promise.race([wsClient.connect(), wsTimeout]);
          }
          setConnectionStatus((prev) => ({ ...prev, websocket: wsClient.isConnected }));
        } catch {
          setConnectionStatus((prev) => ({ ...prev, websocket: false }));
        }
      } else {
        setConnectionStatus((prev) => ({ ...prev, websocket: false }));
      }
    } catch (e) {
      setConnectionStatus((prev) => ({ ...prev, websocket: false }));
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
        // 若 Tauri 管理的后端未运行（例如你手动单独启动了后端），尝试自动发现外部后端端口
        if (!status?.running) {
          const discoveredOk = await autoConfigureBackend();
          if (discoveredOk) {
            // 读取服务端口信息，更新状态
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
              const port = serverInfo?.data?.port ?? 8000;
              status = { running: true, port };
            } catch {
              status = { running: true, port: 8000 };
            }
          }
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


  return (
    <div className="min-h-screen bg-gray-50">
      <MessageHost />
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

        

        {activeTab === "settings" && (
          <SettingsPage
            messages={messages}
            backendStatus={backendStatus}
            connections={connectionStatus}
            onMonitorEnter={refreshConnections}
            onMonitorRefresh={refreshConnections}
          />
        )}

        
      </main>
    </div>
  );
};

export default App;
