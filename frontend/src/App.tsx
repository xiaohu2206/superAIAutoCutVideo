import { Copy, Minus, Square, X } from "lucide-react";
import React, { useEffect, useState } from "react";
import AppLoadingScreen from "./components/AppLoadingScreen";
import Navigation from "./components/Navigation";
import SettingsPage from "./components/settingsPage";
import MessageHost from "./components/ui/MessageHost";
import ProjectEditPage from "./pages/ProjectEditPage";
import ProjectManagementPage from "./pages/ProjectManagementPage";
import { useAppVersion } from "./hooks/useAppVersion";
import {
  TauriCommands,
  WebSocketMessage,
  apiClient,
  autoConfigureBackend,
  configureBackend,
  handshakeVerifyBackend,
  wsClient,
} from "./services/clients";

interface BackendStatus {
  running: boolean;
  port: number;
  pid?: number;
  boot_token?: string;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** 与 tauri.conf 中启动完成后主界面一致（逻辑像素） */
const TAURI_MAIN_WINDOW_INNER = { width: 1280, height: 800 } as const;

const detectTauriEnvironment = (): boolean => {
  const w: any = typeof window !== "undefined" ? window : undefined;
  const hasIpc = typeof w?.__TAURI_IPC__ === "function";
  const hasCoreInvoke = !!w?.__TAURI__?.core?.invoke;
  const hasMeta = !!w?.__TAURI_METADATA__ || !!w?.__TAURI_INTERNALS__;
  return hasIpc || hasCoreInvoke || hasMeta;
};

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
  const { appVersion } = useAppVersion();
  const [isTauri, setIsTauri] = useState<boolean>(() => detectTauriEnvironment());
  const [isMaximized, setIsMaximized] = useState(false);

  // 初始化应用
  useEffect(() => {
    setIsTauri(detectTauriEnvironment());
    const timer = window.setInterval(() => {
      const detected = detectTauriEnvironment();
      setIsTauri((prev) => (prev === detected ? prev : detected));
    }, 300);

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
      window.clearInterval(timer);
      wsClient.off("*", handleWsMessage);
      wsClient.off("open", handleWsOpen);
      wsClient.off("close", handleWsClose);
      wsClient.off("error", handleWsError);
      wsClient.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!isTauri) return;

    let mounted = true;

    const syncMaximizedState = async () => {
      const value = await TauriCommands.isWindowMaximized();
      if (mounted) {
        setIsMaximized(value);
      }
    };

    void syncMaximizedState();

    const handleResize = () => {
      void syncMaximizedState();
    };

    window.addEventListener("resize", handleResize);
    return () => {
      mounted = false;
      window.removeEventListener("resize", handleResize);
    };
  }, [isTauri]);

  const handleToggleMaximize = async () => {
    const nextState = await TauriCommands.toggleMaximizeWindow();
    setIsMaximized(nextState);
  };

  const handleTitlebarPointerDown: React.PointerEventHandler<HTMLDivElement> = (event) => {
    if (!isTauri) return;
    if (event.button !== 0) return;

    const target = event.target as HTMLElement | null;
    if (target?.closest(".titlebar-no-drag")) {
      return;
    }

    void TauriCommands.startDragWindow();
  };

  const initializeApp = async () => {
    setIsLoading(true);

    const expandMainWindowBeforeMainUi = async () => {
      if (!detectTauriEnvironment()) return;
      await TauriCommands.setMainWindowSize(
        TAURI_MAIN_WINDOW_INNER.width,
        TAURI_MAIN_WINDOW_INNER.height,
        true
      );
    };

    let attempts = 0;
    let ready = false;
    const maxAttempts = 30;
    do {
      try {
        const status = await checkBackendStatus();
        const apiOk = await apiClient.testConnection();
        if (status && status.running && apiOk) {
          try {
            const wsTimeout = new Promise((_, reject) =>
              setTimeout(() => reject(new Error("WebSocket连接超时")), 2000)
            );
            await Promise.race([wsClient.connect(), wsTimeout]);
          } catch (e) {
            console.debug("WebSocket连接失败");
          }
          await expandMainWindowBeforeMainUi();
          setIsLoading(false);
          ready = true;
          continue;
        }
      } catch (e) {
        console.debug("初始化中，后端未就绪，继续重试");
      }
      attempts += 1;
      await sleep(Math.min(800 + attempts * 200, 3000));
    } while (!ready && attempts < maxAttempts);
    if (!ready) {
      await expandMainWindowBeforeMainUi();
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
      const isTauriRuntime = detectTauriEnvironment();

      const ensureHandshake = async (s: BackendStatus) => {
        if (!s?.port) return;
        configureBackend(s.port);
        const requireBootTokenNow = isTauriRuntime && import.meta.env.PROD && !!(s.boot_token && String(s.boot_token).trim());
        await handshakeVerifyBackend(apiClient.getBaseUrl(), {
          expectedBootToken: s.boot_token ?? null,
          requireBootToken: requireBootTokenNow,
          timeoutMs: 1200,
        });
      };
      // 检查是否在Tauri环境中
      if (isTauriRuntime) {
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
      <AppLoadingScreen
        appVersion={appVersion}
        updateVersion=""
      />
    );
  }

  const handleHomeClick = () => {
    if (currentProjectId) {
      setCurrentProjectId(null);
      return;
    }
    setActiveTab("home");
  };

  return (
    <div className="window-shell flex h-screen overflow-hidden rounded-[18px] border border-white/55 bg-slate-100 shadow-[0_24px_80px_rgba(15,23,42,0.28)] ring-1 ring-slate-900/5">
      <Navigation
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onHomeClick={handleHomeClick}
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.08),_transparent_30%),linear-gradient(to_bottom,_rgba(255,255,255,0.86),_rgba(248,250,252,0.95))]">
        {isTauri && (
          <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/88 backdrop-blur-xl">
            <div
              className="titlebar-drag flex h-[48px] items-center gap-3 px-1 sm:px-2 lg:px-3"
              onPointerDown={handleTitlebarPointerDown}
            >
              <div className="min-w-0 flex-1 select-none">
                <div className="flex items-center gap-2">
                  <h1 className="truncate text-sm font-semibold tracking-[0.02em] text-slate-900 sm:text-[15px]">
                    SuperAI 影视剪辑
                  </h1>
                  {!!appVersion && (
                    <span className="hidden rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10px] font-medium leading-none text-blue-700 md:inline-flex">
                      v{appVersion}
                    </span>
                  )}
                </div>
              </div>

              <div className="titlebar-no-drag hidden shrink-0 items-center gap-1 sm:flex">
                <button
                  onClick={() => void TauriCommands.minimizeWindow()}
                  className="titlebar-no-drag inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition-all duration-200 hover:bg-slate-100 hover:text-slate-700"
                  title="最小化"
                  aria-label="最小化窗口"
                >
                  <Minus className="h-3 w-3" />
                </button>
                <button
                  onClick={handleToggleMaximize}
                  className="titlebar-no-drag inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition-all duration-200 hover:bg-slate-100 hover:text-slate-700"
                  title={isMaximized ? "还原" : "最大化"}
                  aria-label={isMaximized ? "还原窗口" : "最大化窗口"}
                >
                  {isMaximized ? (
                    <Copy className="h-2.5 w-2.5" />
                  ) : (
                    <Square className="h-2.5 w-2.5" />
                  )}
                </button>
                <button
                  onClick={() => void TauriCommands.closeWindow()}
                  className="titlebar-no-drag inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition-all duration-200 hover:bg-rose-500 hover:text-white"
                  title="关闭"
                  aria-label="关闭窗口"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            </div>
          </header>
        )}

        <main
          className={
            activeTab === "settings"
              ? "main-scroll-hidden flex min-h-0 flex-1 flex-col overflow-hidden"
              : "main-scroll-hidden flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden"
          }
        >
          <div
            className={
              activeTab === "settings"
                ? "scrollbar-hidden flex min-h-0 w-full flex-1 flex-col p-0"
                : "scrollbar-hidden flex min-h-0 w-full flex-1 flex-col px-4 pb-2 pt-2 sm:px-5 lg:px-6 "
            }
          >
      
              <MessageHost />
            <div
              className={
                activeTab === "settings"
                  ? "scrollbar-hidden flex min-h-0 w-full flex-1 flex-col overflow-hidden"
                  : "scrollbar-hidden min-h-0 flex-1 overflow-y-auto overflow-x-hidden"
              }
            >
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
                <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
                  <SettingsPage
                    messages={messages}
                    backendStatus={backendStatus}
                    connections={connectionStatus}
                    onMonitorEnter={refreshConnections}
                    onMonitorRefresh={refreshConnections}
                  />
                </div>
              )}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};

export default App;
