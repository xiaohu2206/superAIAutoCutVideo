import { AlertTriangle, Copy, Minus, Square, X } from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import AppLoadingScreen, { type BackendExtractProgress } from "./components/AppLoadingScreen";
import Navigation from "./components/Navigation";
import SettingsPage from "./components/settingsPage";
import MessageHost from "./components/ui/MessageHost";
import ProjectEditPage from "./pages/ProjectEditPage";
import ProjectManagementPage from "./pages/ProjectManagementPage";
import UserProfile from "./components/auth/UserProfile";
import { useAppVersion } from "./hooks/useAppVersion";
import TaskQueueFloatingBall from "./components/projectEdit/TaskQueueFloatingBall";
import {
  type BackendReadyPayload,
  type BackendResourceStatus,
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

type ThemeMode = "light" | "dark";

const THEME_STORAGE_KEY = "sacv_theme";

const getInitialTheme = (): ThemeMode => {
  if (typeof window === "undefined") return "dark";

  try {
    const savedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (savedTheme === "light" || savedTheme === "dark") {
      return savedTheme;
    }
  } catch {
    /* localStorage may be unavailable in restricted webviews */
  }

  return "dark";
};

const applyTheme = (theme: ThemeMode) => {
  if (typeof document === "undefined") return;

  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.style.colorScheme = theme;
};

/** 与 tauri.conf 首屏 loading 小窗一致（逻辑像素） */
const TAURI_LOADING_WINDOW_INNER = { width: 800, height: 350 } as const;

/** 与 tauri.conf 中启动完成后主界面一致（逻辑像素） */
const TAURI_MAIN_WINDOW_INNER = { width: 1280, height: 800 } as const;

/** 首屏连接后端：总体最长等待（GPU 冷启动可能数分钟） */
const STARTUP_OVERALL_MS = 420_000;
/** 首屏轮询后端 HTTP 就绪的间隔 */
const STARTUP_POLL_MS = 800;
/** 加载页出现「跳过等待」按钮前的最短等待 */
const LOADING_SKIP_VISIBLE_MS = 45_000;

function statusFromReadyPayload(payload: BackendReadyPayload): BackendStatus {
  return {
    running: true,
    port: payload.port,
    boot_token: payload.boot_token ?? undefined,
  };
}

async function withTimeoutOrNull<T>(promise: Promise<T>, timeoutMs: number): Promise<T | null> {
  let timeoutId: number | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<null>((resolve) => {
        timeoutId = window.setTimeout(() => resolve(null), timeoutMs);
      }),
    ]);
  } catch {
    return null;
  } finally {
    if (timeoutId !== undefined) {
      window.clearTimeout(timeoutId);
    }
  }
}

async function fetchOkWithTimeout(url: string, timeoutMs: number): Promise<boolean> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
    });
    return response.ok;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function getConfiguredBackendPort(): number | null {
  try {
    const port = Number(new URL(apiClient.getBaseUrl()).port || 0);
    return port > 0 ? port : null;
  } catch {
    return null;
  }
}

/** WebView 直接探活兜底：只要 /api/hello 已通，就不要继续卡在首屏。 */
async function probeBackendByHello(): Promise<BackendStatus | null> {
  const configuredPort = getConfiguredBackendPort();
  const ports = Array.from(
    new Set([
      configuredPort,
      18000,
      8000,
      ...Array.from({ length: 20 }, (_, i) => 18001 + i),
      ...Array.from({ length: 10 }, (_, i) => 8001 + i),
    ].filter((p): p is number => typeof p === "number" && p > 0))
  );

  return new Promise((resolve) => {
    let pending = ports.length;
    let settled = false;

    for (const port of ports) {
      const baseUrl = `http://127.0.0.1:${port}`;
      void (async () => {
        try {
          try {
            const info = await handshakeVerifyBackend(baseUrl, {
              requireBootToken: false,
              timeoutMs: 700,
            });
            if (!settled) {
              settled = true;
              resolve({ running: true, port: info.port || port, boot_token: info.boot_token });
            }
            return;
          } catch {
            if (await fetchOkWithTimeout(`${baseUrl}/api/hello`, 700)) {
              if (!settled) {
                settled = true;
                resolve({ running: true, port });
              }
              return;
            }
          }
        } catch {
          /* ignore this port */
        } finally {
          pending -= 1;
          if (!settled && pending <= 0) {
            settled = true;
            resolve(null);
          }
        }
      })();
    }
  });
}

/** 首屏探测：优先 Rust 缓存/探活，再回退 WebView 端口扫描 */
async function probeBackendReady(): Promise<BackendStatus | null> {
  const probes: Array<Promise<BackendStatus | null>> = [probeBackendByHello()];

  if (detectTauriEnvironment()) {
    probes.push((async () => {
    try {
      const pending = await withTimeoutOrNull(TauriCommands.takePendingBackendReady(), 800);
      if (pending?.port) {
        return statusFromReadyPayload(pending);
      }
    } catch {
      /* ignore */
    }
    try {
      const peek = await withTimeoutOrNull(TauriCommands.probeBackendHttpReady(), 1200);
      if (peek?.running && peek.port) {
        return { running: true, port: peek.port, boot_token: peek.boot_token };
      }
    } catch {
      /* ignore */
    }
    return null;
    })());
  }

  probes.push((async () => {
  if (await withTimeoutOrNull(autoConfigureBackend(), 2500)) {
    try {
      const info = await withTimeoutOrNull(handshakeVerifyBackend(apiClient.getBaseUrl(), {
        requireBootToken: false,
        timeoutMs: 2500,
      }), 3000);
      if (!info) return null;
      const port =
        info.port ||
        Number(new URL(apiClient.getBaseUrl()).port || 0) ||
        (import.meta.env.DEV ? 8000 : 18000);
      return { running: true, port, boot_token: info.boot_token };
    } catch {
      /* fall through */
    }
  }
  return null;
  })());

  return new Promise((resolve) => {
    let pending = probes.length;
    let settled = false;
    for (const probe of probes) {
      void probe.then((status) => {
        if (!settled && status?.running && status.port) {
          settled = true;
          resolve(status);
        }
      }).catch(() => {
        /* ignore this probe */
      }).finally(() => {
        pending -= 1;
        if (!settled && pending <= 0) {
          settled = true;
          resolve(null);
        }
      });
    }
  });
}

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
  const [loadingElapsedSeconds, setLoadingElapsedSeconds] = useState(0);
  const [backendExtractProgress, setBackendExtractProgress] = useState<BackendExtractProgress | null>(null);
  const [backendResourceStatus, setBackendResourceStatus] = useState<BackendResourceStatus | null>(null);
  const [showBackendStartupBanner, setShowBackendStartupBanner] = useState(false);
  const [activeTab, setActiveTab] = useState("home");
  const [currentProjectId, setCurrentProjectId] = useState<string | null>(null);
  const [showProfile, setShowProfile] = useState(false);
  const [theme, setTheme] = useState<ThemeMode>(() => getInitialTheme());
  const { appVersion } = useAppVersion();
  const [isTauri, setIsTauri] = useState<boolean>(() => detectTauriEnvironment());
  const [isMaximized, setIsMaximized] = useState(false);
  const startupInitStartedRef = useRef(false);

  useEffect(() => {
    applyTheme(theme);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      /* ignore storage failures */
    }
  }, [theme]);

  const handleToggleTheme = () => {
    setTheme((current) => (current === "dark" ? "light" : "dark"));
  };

  // 初始化应用
  useEffect(() => {
    if (startupInitStartedRef.current) {
      return;
    }
    startupInitStartedRef.current = true;

    let mounted = true;
    let backendProgressUnlisten: UnlistenFn | null = null;

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

    const setupStartupListeners = async () => {
      if (detectTauriEnvironment()) {
        const unlisten = await listen<BackendExtractProgress>("backend-extract-progress", (event) => {
          if (!mounted) return;
          setBackendExtractProgress(event.payload);
        });
        if (mounted) {
          backendProgressUnlisten = unlisten;
        } else {
          unlisten();
        }
      }
      if (mounted) {
        void initializeApp(() => mounted);
      }
    };

    void setupStartupListeners();

    return () => {
      mounted = false;
      window.clearInterval(timer);
      backendProgressUnlisten?.();
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

  useEffect(() => {
    if (!isLoading) return;
    setLoadingElapsedSeconds(0);
    const id = window.setInterval(() => {
      setLoadingElapsedSeconds((s) => s + 1);
    }, 1000);
    return () => window.clearInterval(id);
  }, [isLoading]);

  useEffect(() => {
    if (!isLoading || !isTauri) return;
    void TauriCommands.setMainWindowSize(
      TAURI_LOADING_WINDOW_INNER.width,
      TAURI_LOADING_WINDOW_INNER.height,
      true,
    ).catch((error) => {
      console.debug("首屏加载窗口居中失败:", error);
    });
  }, [isLoading, isTauri]);

  useEffect(() => {
    if (!isLoading || !isTauri) return;
    let mounted = true;

    const refresh = async () => {
      try {
        const status = await TauriCommands.getBackendResourceStatus();
        if (mounted) setBackendResourceStatus(status);
      } catch (error) {
        console.debug("读取后端资源状态失败:", error);
      }
    };

    void refresh();
    const id = window.setInterval(refresh, 1000);
    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, [isLoading, isTauri]);

  useEffect(() => {
    if (!isLoading) return;
    let mounted = true;

    const completeFromHttpProbe = async () => {
      const status = await probeBackendByHello();
      if (!mounted || !status?.running || !status.port) return;
      configureBackend(status.port);
      setBackendStatus(status);
      setConnectionStatus((prev) => ({ ...prev, backend: true, api: true }));
      setShowBackendStartupBanner(false);
      setBackendExtractProgress(null);
      setBackendResourceStatus(null);
      setIsLoading(false);
      if (detectTauriEnvironment()) {
        void TauriCommands.setMainWindowSize(
          TAURI_MAIN_WINDOW_INNER.width,
          TAURI_MAIN_WINDOW_INNER.height,
          true
        ).catch((error) => {
          console.debug("HTTP探活成功后调整主窗口尺寸失败，继续进入主界面:", error);
        });
      }
    };

    void completeFromHttpProbe();
    const id = window.setInterval(() => {
      void completeFromHttpProbe();
    }, 1000);

    return () => {
      mounted = false;
      window.clearInterval(id);
    };
  }, [isLoading]);

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

  const initializeApp = async (isMounted: () => boolean = () => true) => {
    setIsLoading(true);
    setBackendExtractProgress(null);
    setBackendResourceStatus(null);
    setShowBackendStartupBanner(false);

    const expandMainWindowBeforeMainUi = async () => {
      if (!detectTauriEnvironment()) return;
      try {
        await TauriCommands.setMainWindowSize(
          TAURI_MAIN_WINDOW_INNER.width,
          TAURI_MAIN_WINDOW_INNER.height,
          true
        );
      } catch (error) {
        console.debug("调整主窗口尺寸失败，继续进入主界面:", error);
      }
    };

    let startupDone = false;
    let backendReadyUnlisten: UnlistenFn | null = null;

    const completeStartup = async (status: BackendStatus) => {
      if (!isMounted() || startupDone) return;
      startupDone = true;
      configureBackend(status.port);
      setBackendStatus(status);
      setConnectionStatus((prev) => ({ ...prev, backend: true, api: true }));
      setShowBackendStartupBanner(false);
      setBackendExtractProgress(null);
      setBackendResourceStatus(null);
      // 先退出 loading，避免窗口调整/WebSocket 阻塞首屏
      setIsLoading(false);
      void expandMainWindowBeforeMainUi();
      void (async () => {
        try {
          const wsTimeout = new Promise((_, reject) =>
            setTimeout(() => reject(new Error("WebSocket连接超时")), 2000)
          );
          await Promise.race([wsClient.connect(), wsTimeout]);
        } catch {
          console.debug("WebSocket连接失败，进入主界面后重试");
        }
      })();
    };

    if (detectTauriEnvironment()) {
      try {
        const pending = await TauriCommands.takePendingBackendReady();
        if (pending?.port) {
          await completeStartup(statusFromReadyPayload(pending));
          return;
        }
      } catch (error) {
        console.debug("读取缓存 backend-ready 失败:", error);
      }

      try {
        backendReadyUnlisten = await listen<BackendReadyPayload>("backend-ready", (event) => {
          const { port, boot_token } = event.payload;
          if (!port) return;
          void completeStartup({
            running: true,
            port,
            boot_token: boot_token ?? undefined,
          });
        });
      } catch (error) {
        console.debug("监听 backend-ready 失败，将仅使用轮询:", error);
      }

      void TauriCommands.startBackend()
        .then((status) => {
          if (status?.running && status.port) {
            void completeStartup(status);
          }
        })
        .catch((error) => {
          console.debug("后台启动后端:", error);
        });
    }

    const startedAt = Date.now();

    try {
      while (!startupDone && Date.now() - startedAt < STARTUP_OVERALL_MS) {
        const status = await probeBackendReady();
        if (status?.running && status.port) {
          await completeStartup(status);
          break;
        }
        await sleep(STARTUP_POLL_MS);
      }
    } finally {
      backendReadyUnlisten?.();
    }

    if (!startupDone) {
      await expandMainWindowBeforeMainUi();
      setIsLoading(false);
      if (detectTauriEnvironment()) {
        setShowBackendStartupBanner(true);
      }
    }
  };

  const handleSkipLoadingToMain = () => {
    void (async () => {
      const status = await probeBackendReady();
      if (status?.port) {
        configureBackend(status.port);
        setBackendStatus(status);
        setConnectionStatus((prev) => ({ ...prev, backend: true, api: true }));
      }
      if (detectTauriEnvironment()) {
        try {
          await TauriCommands.setMainWindowSize(
            TAURI_MAIN_WINDOW_INNER.width,
            TAURI_MAIN_WINDOW_INNER.height,
            true
          );
        } catch (error) {
          console.debug("跳过加载时调整主窗口尺寸失败，继续进入主界面:", error);
        }
        setShowBackendStartupBanner(!status?.running);
      }
      setBackendExtractProgress(null);
      setBackendResourceStatus(null);
      setIsLoading(false);
    })();
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

  const retryBackendConnection = async () => {
    try {
      await refreshConnections();
      const status = await checkBackendStatus();
      const apiOk = await apiClient.testConnection();
      if (status?.running && apiOk) {
        setShowBackendStartupBanner(false);
        setConnectionStatus((prev) => ({ ...prev, backend: true, api: true }));
      }
    } catch {
      /* 保持横幅，由用户在设置中查看详情 */
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
        let handshakeOk = false;
        if (status?.running && status.port) {
          try {
            await ensureHandshake(status);
            handshakeOk = true;
          } catch (error) {
            console.debug("后端进程存在但握手未通过，将尝试启动/等待就绪:", error);
          }
        }
        if (!handshakeOk) {
          try {
            const started = await TauriCommands.startBackend();
            if (!started?.running || !started.port) {
              throw new Error("后端未能启动");
            }
            status = started;
            await ensureHandshake(status);
          } catch (e) {
            const errMsg = e instanceof Error ? e.message : String(e);
            if (errMsg.includes("正在启动中")) {
              for (let i = 0; i < 8; i++) {
                await sleep(1500);
                const pending = await TauriCommands.getBackendStatus();
                if (pending?.running && pending.port) {
                  status = pending;
                  await ensureHandshake(status);
                  break;
                }
              }
              if (!status?.running) {
                throw e;
              }
            } else {
              const discoveredOk = await autoConfigureBackend();
              if (discoveredOk) {
                const info = await handshakeVerifyBackend(apiClient.getBaseUrl(), {
                  requireBootToken: false,
                  timeoutMs: 2000,
                });
                status = { running: true, port: info.port, boot_token: info.boot_token ?? undefined };
              } else {
                throw e;
              }
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
        elapsedSeconds={loadingElapsedSeconds}
        backendExtractProgress={backendExtractProgress}
        backendResourceStatus={backendResourceStatus}
        showSkipAfterMs={LOADING_SKIP_VISIBLE_MS}
        onSkipToMain={handleSkipLoadingToMain}
      />
    );
  }

  const handleHomeClick = () => {
    if (showProfile) {
      setShowProfile(false);
      return;
    }
    if (currentProjectId) {
      setCurrentProjectId(null);
      return;
    }
    setActiveTab("home");
  };

  return (
    <div className="window-shell flex h-screen overflow-hidden rounded-[18px] border border-white/55 bg-slate-100 shadow-[0_24px_80px_rgba(15,23,42,0.28)] ring-1 ring-slate-900/5 dark:border-white/10 dark:bg-[#121212] dark:shadow-[0_24px_80px_rgba(0,0,0,0.65)] dark:ring-white/10">
      <Navigation
        activeTab={showProfile ? "profile" : activeTab}
        onTabChange={(tab) => {
          setShowProfile(false);
          setActiveTab(tab);
        }}
        onHomeClick={handleHomeClick}
        onProfileClick={() => setShowProfile(true)}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-[radial-gradient(circle_at_top,_rgba(59,130,246,0.08),_transparent_30%),linear-gradient(to_bottom,_rgba(255,255,255,0.86),_rgba(248,250,252,0.95))] dark:bg-[radial-gradient(circle_at_top,_rgba(37,99,235,0.10),_transparent_28%),linear-gradient(to_bottom,_#181818,_#121212)]">
        {isTauri && (
          <header className="sticky top-0 z-50 border-b border-slate-200/80 bg-white/88 backdrop-blur-xl dark:border-white/10 dark:bg-[#181818]/88">
            <div
              className="titlebar-drag flex h-[48px] items-center gap-3 px-1 sm:px-2 lg:px-3"
              onPointerDown={handleTitlebarPointerDown}
            >
              <div className="min-w-0 flex-1 select-none">
                <div className="flex items-center gap-2">
                  <h1 className="truncate text-sm font-semibold tracking-[0.02em] text-slate-900 dark:text-zinc-100 sm:text-[15px]">
                    SuperAI 影视剪辑
                  </h1>
                  {!!appVersion && (
                    <span className="hidden rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10px] font-medium leading-none text-blue-700 dark:border-blue-400/20 dark:bg-blue-500/10 dark:text-blue-300 md:inline-flex">
                      v{appVersion}
                    </span>
                  )}
                </div>
              </div>

              <div className="titlebar-no-drag hidden shrink-0 items-center gap-1 sm:flex">
                <button
                  onClick={() => void TauriCommands.minimizeWindow()}
                  className="titlebar-no-drag inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition-all duration-200 hover:bg-slate-100 hover:text-slate-700 dark:text-zinc-500 dark:hover:bg-white/10 dark:hover:text-zinc-100"
                  title="最小化"
                  aria-label="最小化窗口"
                >
                  <Minus className="h-3 w-3" />
                </button>
                <button
                  onClick={handleToggleMaximize}
                  className="titlebar-no-drag inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition-all duration-200 hover:bg-slate-100 hover:text-slate-700 dark:text-zinc-500 dark:hover:bg-white/10 dark:hover:text-zinc-100"
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
                  className="titlebar-no-drag inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-400 transition-all duration-200 hover:bg-rose-500 hover:text-white dark:text-zinc-500"
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
                ? "scrollbar-hidden flex min-h-0 w-full flex-1 flex-col p-0 dark:bg-[#121212]"
                : "scrollbar-hidden flex min-h-0 w-full flex-1 flex-col px-4 pb-2 pt-2 sm:px-5 lg:px-6 dark:bg-[#121212]"
            }
          >
            {isTauri && showBackendStartupBanner && (
              <div
                className="mb-3 flex flex-col gap-2 rounded-xl border border-amber-200/90 bg-amber-50/95 px-3 py-2.5 text-amber-950 shadow-sm dark:border-amber-400/20 dark:bg-amber-500/10 dark:text-amber-100 sm:flex-row sm:items-center sm:justify-between"
                role="alert"
              >
                <div className="flex min-w-0 gap-2">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden />
                  <div className="min-w-0 text-[12px] leading-snug">
                    <span className="font-medium">本地后端未就绪</span>
                    <span className="text-amber-900/90 dark:text-amber-100/90">
                      {" "}
                      若已放行杀软仍无法连接，请查看临时目录日志{" "}
                      <span className="break-all font-mono text-[11px]">super_auto_cut_backend.log</span>
                      后重试。
                    </span>
                  </div>
                </div>
                <div className="flex shrink-0 gap-2 sm:justify-end">
                  <button
                    type="button"
                    className="titlebar-no-drag rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700"
                    onClick={() => void retryBackendConnection()}
                  >
                    重试连接
                  </button>
                  <button
                    type="button"
                    className="titlebar-no-drag rounded-lg border border-amber-300/80 bg-white px-3 py-1.5 text-xs font-medium text-amber-900 hover:bg-amber-100/80 dark:border-amber-400/30 dark:bg-white/5 dark:text-amber-50 dark:hover:bg-amber-500/15"
                    onClick={() => setShowBackendStartupBanner(false)}
                  >
                    关闭提示
                  </button>
                </div>
              </div>
            )}
      
              <MessageHost />
            <div
              className={
                activeTab === "settings"
                  ? "scrollbar-hidden flex min-h-0 w-full flex-1 flex-col overflow-hidden"
                  : "scrollbar-hidden min-h-0 flex-1 overflow-y-auto overflow-x-hidden"
              }
            >
              <div
                className={
                  activeTab === "home" && !currentProjectId && !showProfile
                    ? "contents"
                    : "hidden"
                }
                aria-hidden={activeTab !== "home" || !!currentProjectId || showProfile}
              >
                <ProjectManagementPage
                  onEditProject={(projectId) => setCurrentProjectId(projectId)}
                  onShowLogin={() => {
                    const event = new CustomEvent("sacv:show-login-modal");
                    window.dispatchEvent(event);
                  }}
                  onShowProfile={() => setShowProfile(true)}
                />
              </div>

              {activeTab === "home" && currentProjectId && !showProfile && (
                <ProjectEditPage
                  projectId={currentProjectId}
                  onBack={() => setCurrentProjectId(null)}
                  onShowLogin={() => {
                    const event = new CustomEvent("sacv:show-login-modal");
                    window.dispatchEvent(event);
                  }}
                  onShowProfile={() => setShowProfile(true)}
                />
              )}

              {showProfile && (
                <UserProfile onBack={() => setShowProfile(false)} />
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
        <TaskQueueFloatingBall />
      </div>
    </div>
  );
};

export default App;
