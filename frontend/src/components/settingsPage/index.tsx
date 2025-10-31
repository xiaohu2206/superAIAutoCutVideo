import { Info, RotateCcw, Save, Settings } from "lucide-react";
import React, { useState } from "react";
import { BackendSettings } from "./components/BackendSettings";
import { ContentModelSettings } from "./components/ContentModelSettings";
import { PathSettings } from "./components/PathSettings";
import { VideoModelSettings } from "./components/VideoModelSettings";
import { sections } from "./constants";
import { useContentModelConfig } from "./hooks/useContentModelConfig";
import { useSettings } from "./hooks/useSettings";
import { useVideoModelConfig } from "./hooks/useVideoModelConfig";

/**
 * 设置页面主组件
 */
const SettingsPage: React.FC = () => {
  const [activeSection, setActiveSection] = useState("backend");

  // 使用自定义 Hooks
  const {
    settings,
    hasChanges,
    isSaving,
    saveSettings,
    resetSettings,
    updateSetting,
    selectDirectory,
  } = useSettings();

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
    showContentPassword,
    setShowContentPassword,
    handleContentProviderChange,
    updateCurrentContentConfig,
    testContentModelConnection,
  } = useContentModelConfig();

  // 渲染当前激活的设置区域内容
  const renderSectionContent = () => {
    switch (activeSection) {
      case "backend":
        return (
          <BackendSettings
            settings={settings}
            updateSetting={updateSetting}
          />
        );
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
            showContentPassword={showContentPassword}
            setShowContentPassword={setShowContentPassword}
            handleContentProviderChange={handleContentProviderChange}
            updateCurrentContentConfig={updateCurrentContentConfig}
            testContentModelConnection={testContentModelConnection}
          />
        );
      case "paths":
        return (
          <PathSettings
            settings={settings}
            updateSetting={updateSetting}
            selectDirectory={selectDirectory}
          />
        );
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
                {isSaving ? "保存中..." : "保存设置"}
              </button>
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

