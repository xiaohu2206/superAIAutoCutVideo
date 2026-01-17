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
  handshakeVerifyBackend,
  wsClient,
} from "./services/clients";
import { message } from "./services/message";

interface BackendStatus {
  running: boolean;
  port: number;
  pid?: number;
  boot_token?: string;
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
  const [initPhase, setInitPhase] = useState("初始化");
  const [initError, setInitError] = useState<string | null>(null);
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
      setInitError(null);
      setInitPhase("检查后端服务");

      const status = await checkBackendStatus();
      setInitPhase("检查 API 连接");
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
      const errMsg = error instanceof Error ? error.message : String(error || "初始化失败");
      console.error("初始化应用失败:", error);
      setInitError(errMsg);
      message.error(`${errMsg}（可查看临时日志 super_auto_cut_backend.log）`, 5);
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
      setConnectionStatus((prev) => ({ ...prev, backend: false, api: false, websocket: false }));
    }
  };

  const checkBackendStatus = async (): Promise<BackendStatus | null> => {
    try {
      let status: BackendStatus;
      const isTauri = typeof (window as any).__TAURI_IPC__ === "function";
      const requireBootToken = isTauri && import.meta.env.PROD;

      const ensureHandshake = async (s: BackendStatus) => {
        if (!s?.port) return;
        configureBackend(s.port);
        await handshakeVerifyBackend(apiClient.getBaseUrl(), {
          expectedBootToken: s.boot_token ?? null,
          requireBootToken,
          timeoutMs: 1200,
        });
      };
      // 检查是否在Tauri环境中
      if (isTauri) {
        status = await TauriCommands.getBackendStatus();
        if (status?.running && status.port) {
          await ensureHandshake(status);
        }
        if (!status?.running) {
          try {
            const started = await TauriCommands.startBackend();
            if (!started?.running || !started.port) {
              throw new Error("后端未能启动");
            }
            status = started;
            await ensureHandshake(status);
          } catch (e) {
            if (import.meta.env.DEV) {
              const discoveredOk = await autoConfigureBackend();
              if (discoveredOk) {
                const info = await handshakeVerifyBackend(apiClient.getBaseUrl(), {
                  requireBootToken: false,
                  timeoutMs: 1200,
                });
                status = { running: true, port: info.port };
              } else {
                throw e;
              }
            } else {
              throw e;
            }
          }
        }
      } else {
        // 在浏览器环境中，尝试自动发现后端端口
        console.log("浏览器环境，尝试自动发现后端端口...");
        const discovered = await autoConfigureBackend();
        if (discovered) {
          const info = await handshakeVerifyBackend(apiClient.getBaseUrl(), {
            requireBootToken: false,
            timeoutMs: 1200,
          });
          status = { running: true, port: info.port };
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
      throw error;
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
          <p className="text-gray-600">{initPhase}...</p>
        </div>
      </div>
    );
  }

  if (initError) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-6">
        <div className="max-w-xl w-full bg-white border border-gray-200 rounded-lg shadow-sm p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">后端启动失败</h2>
          <p className="text-sm text-gray-700 break-words">{initError}</p>
          <p className="text-sm text-gray-500 mt-2 break-words">
            可查看临时日志：super_auto_cut_backend.log
          </p>
          <div className="mt-4 flex gap-3">
            <button
              onClick={initializeApp}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              重试
            </button>
            <button
              onClick={() => setInitError(null)}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
            >
              继续进入
            </button>
          </div>
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
