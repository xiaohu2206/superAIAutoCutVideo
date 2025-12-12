import { Settings } from "lucide-react";
import React, { useState } from "react";
import { WebSocketMessage } from "../../services/clients";
import AboutSection from "./components/AboutSection";
import { ContentModelSettings } from "./components/models/content/ContentModelSettings";
import { VideoModelSettings } from "./components/models/video/VideoModelSettings";
import MonitorSection from "./components/MonitorSection";
import { TtsSettings } from "./components/tts/TtsSettings";
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
}

const SettingsPage: React.FC<SettingsPageProps> = ({
  messages = [],
  backendStatus = { running: false, port: 8000 },
  connections = { api: false, websocket: false },
}) => {
  const [activeSection, setActiveSection] = useState(sections[0].id);


  const {
    selectedProvider,
    currentConfig,
    setCurrentConfig,
    testingConnection,
    testResult,
    showPassword,
    setShowPassword,
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
    showContentPassword,
    setShowContentPassword,
    handleContentProviderChange,
    updateCurrentContentConfig,
    testContentModelConnection,
  } = useContentModelConfig();

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
            showPassword={showPassword}
            setShowPassword={setShowPassword}
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
            showContentPassword={showContentPassword}
            setShowContentPassword={setShowContentPassword}
            handleContentProviderChange={handleContentProviderChange}
            updateCurrentContentConfig={updateCurrentContentConfig}
            testContentModelConnection={testContentModelConnection}
          />
        );
      case "tts":
        return <TtsSettings />;
      case "monitor":
        return (
          <MonitorSection
            messages={messages as any}
            backendStatus={backendStatus}
            connections={connections}
          />
        );
      case "about":
        return <AboutSection />;
      default:
        return null;
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="bg-white rounded-lg shadow-md overflow-hidden">
        {/* 头部 */}
        <div className="px-6 py-4 bg-gray-50 border-b">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Settings className="h-6 w-6 text-gray-600" />
              <h2 className="text-xl font-semibold text-gray-900">设置</h2>
            </div>
          </div>
        </div>

        <div className="flex">
          {/* 侧边栏 */}
          <div className="w-64 bg-gray-50 border-r">
            <nav className="p-4 space-y-1">
              {sections.map((section) => {
                const Icon = section.icon;
                const isActive = activeSection === section.id;

                return (
                  <button
                    key={section.id}
                    onClick={() => setActiveSection(section.id)}
                    className={`
                      w-full flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-colors
                      ${
                        isActive
                          ? "bg-blue-100 text-blue-700"
                          : "text-gray-600 hover:text-gray-900 hover:bg-gray-100"
                      }
                    `}
                  >
                    <Icon
                      className={`h-4 w-4 mr-3 ${
                        isActive ? "text-blue-600" : "text-gray-500"
                      }`}
                    />
                    {section.label}
                  </button>
                );
              })}
            </nav>
          </div>

          {/* 主内容区 */}
          <div className="flex-1 p-6">
            <div className="max-w-2xl">
              <h3 className="text-lg font-medium text-gray-900 mb-6">
                {sections.find((s) => s.id === activeSection)?.label}
              </h3>

              {renderSectionContent()}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;

