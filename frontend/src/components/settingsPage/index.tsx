import React, { useEffect, useState } from "react";
import { WebSocketMessage } from "../../services/clients";
import AboutSection from "./components/AboutSection";
import { JianyingDraftPathSection } from "./components/JianyingDraftPathSection";
import { ContentModelSettings } from "./components/models/content/ContentModelSettings";
import { VideoModelSettings } from "./components/models/video/VideoModelSettings";
import MonitorSection from "./components/MonitorSection";
import StorageSettingsSection from "./components/StorageSettingsSection";
import { TtsSettings } from "./components/tts/TtsSettings";
import SubtitleAsrSettings from "@/features/subtitleAsr/components/SubtitleAsrSettings";
import { GlobalParamsSettings } from "./components/GlobalParamsSettings";
import { sections } from "./constants";
import { useContentModelConfig } from "./hooks/useContentModelConfig";
import { useVideoModelConfig } from "./hooks/useVideoModelConfig";

/**
 * 设置页面主组件
 */
interface SettingsPageProps {
  messages?: WebSocketMessage[];
  backendStatus?: { running: boolean; port: number; pid?: number };
  connections?: { api: boolean; websocket: boolean };
  onMonitorEnter?: () => void;
  onMonitorRefresh?: () => Promise<void> | void;
}

const SettingsPage: React.FC<SettingsPageProps> = ({ 
  messages = [],
  backendStatus = { running: false, port: 8000 },
  connections = { api: false, websocket: false },
  onMonitorEnter,
  onMonitorRefresh,
}) => {
  const [activeSection, setActiveSection] = useState(sections[0].id);

  const {
    selectedProvider,
    currentConfig,
    setCurrentConfig,
    testingConnection,
    testResult,
    handleProviderChange,
    updateCurrentConfig,
    testModelConnection,
  } = useVideoModelConfig();

  const {
    contentSelectedProvider,
    currentContentConfig,
    setCurrentContentConfig,
    testingContentConnection,
    contentTestResult,
    contentTestStructured,
    handleContentProviderChange,
    updateCurrentContentConfig,
    testContentModelConnection,
  } = useContentModelConfig();

  useEffect(() => {
    if (activeSection === "monitor") {
      onMonitorEnter?.();
    }
  }, [activeSection]);

  const activeLabel =
    sections.find((s) => s.id === activeSection)?.label ?? "设置";

  // 渲染当前激活的设置区域内容
  const renderSectionContent = () => {
    switch (activeSection) {
      case "videoModel":
        return (
          <VideoModelSettings
            selectedProvider={selectedProvider}
            currentConfig={currentConfig}
            setCurrentConfig={setCurrentConfig}
            testingConnection={testingConnection}
            testResult={testResult}
            handleProviderChange={handleProviderChange}
            updateCurrentConfig={updateCurrentConfig}
            testModelConnection={testModelConnection}
          />
        );
      case "contentModel":
        return (
          <ContentModelSettings
            contentSelectedProvider={contentSelectedProvider}
            currentContentConfig={currentContentConfig}
            setCurrentContentConfig={setCurrentContentConfig}
            testingContentConnection={testingContentConnection}
            contentTestResult={contentTestResult}
            contentTestStructured={contentTestStructured}
            handleContentProviderChange={handleContentProviderChange}
            updateCurrentContentConfig={updateCurrentContentConfig}
            testContentModelConnection={testContentModelConnection}
          />
        );
      case "jianyingDraftPath":
        return <JianyingDraftPathSection />;
      case "tts":
        return <TtsSettings />;
      case "subtitleAsr":
        return <SubtitleAsrSettings />;
      case "storage":
        return <StorageSettingsSection />;
      case "globalParams":
        return <GlobalParamsSettings />;
      case "monitor":
        return (
          <MonitorSection
            messages={messages as any}
            backendStatus={backendStatus}
            connections={connections}
            onRefresh={onMonitorRefresh}
          />
        );
      case "about":
        return <AboutSection />;
      default:
        return null;
    }
  };

  return (
    <div className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col">
      <div className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col md:flex-row md:items-stretch">
        {/* 左侧：分区导航（md+ 固定宽度；长页滚动时侧栏 sticky） */}
        <aside
          className={`
            shrink-0 self-stretch border-b border-slate-200/80 bg-slate-50/90 md:sticky md:top-0 md:z-10 md:w-[232px] md:border-b-0 md:border-r
          `}
        >
          <div className="border-b border-slate-200/60 px-4 py-4">
            <div className="flex items-center gap-3">
              <div className="min-w-0">
                <h2 className="text-base font-semibold tracking-tight text-slate-900">
                  设置
                </h2>
              </div>
            </div>
          </div>

          <nav className="flex flex-col gap-1 p-3" aria-label="设置分区">
            {sections.map((section) => {
              const Icon = section.icon;
              const isActive = activeSection === section.id;

              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActiveSection(section.id)}
                  aria-current={isActive ? "page" : undefined}
                  className={`
                    flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition-colors
                    ${
                      isActive
                        ? "bg-blue-50 text-blue-800 ring-1 ring-blue-200/80"
                        : "text-slate-600 hover:bg-white/80 hover:text-slate-900"
                    }
                  `}
                >
                  <Icon
                    className={`h-4 w-4 shrink-0 ${
                      isActive ? "text-blue-600" : "text-slate-400"
                    }`}
                    aria-hidden
                  />
                  {section.label}
                </button>
              );
            })}
          </nav>
        </aside>

        {/* 右侧：分区标题 + 表单内容（与 App 主区域共用外层滚动） */}
        <section className="scrollbar-hidden flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto overflow-x-hidden bg-white/70">
          <header className="border-b border-slate-100 px-5 py-4 sm:px-6">
            <h3 className="text-lg font-semibold tracking-tight text-slate-900">
              {activeLabel}
            </h3>
          </header>
          <div className="flex flex-1 flex-col px-5 py-6 sm:px-6">
            <div className="mx-auto flex w-full min-w-0 max-w-4xl flex-1 flex-col">
              {renderSectionContent()}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default SettingsPage;
