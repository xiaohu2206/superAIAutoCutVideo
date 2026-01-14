import { useEffect, useState } from "react";
import { message } from "../../../services/message";
import { videoModelService } from "../../../services/videoModelService";
import type { TestResult, VideoModelConfig } from "../types";
import {
    getConfigIdByProvider,
    getDefaultBaseUrl,
    getDefaultDescription,
    getDefaultModelName,
} from "../utils";

/**
 * 视频生成模型配置管理 Hook
 */
export const useVideoModelConfig = () => {
  const [selectedProvider, setSelectedProvider] = useState<string>("qwen");
  const [modelConfigs, setModelConfigs] = useState<
    Record<string, VideoModelConfig>
  >({});
  const [currentConfig, setCurrentConfig] = useState<VideoModelConfig>({
    provider: "qwen",
    api_key: "",
    base_url: "",
    model_name: "",
    extra_params: {},
    description: "",
  });
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<TestResult | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    loadVideoAnalysisConfigs();
  }, []);

  const loadVideoAnalysisConfigs = async () => {
    try {
      const response = await videoModelService.getConfigs();
      if (response.success) {
        const configs = response.data.configs;
        setModelConfigs(configs);

        // 使用 enabled 为 true 的配置作为当前配置
        if (Object.keys(configs).length > 0) {
          // 查找 enabled 为 true 的配置
          const enabledConfigId = Object.keys(configs).find(
            (id) => configs[id].enabled === true
          );

          // 如果找到启用的配置，使用它；否则使用第一个配置
          const activeConfigId = enabledConfigId || Object.keys(configs)[0];
          const activeConfig = configs[activeConfigId];
          setSelectedProvider(activeConfig.provider);
          setCurrentConfig(activeConfig);
        }
      }
    } catch (error) {
      console.error("加载视频生成模型配置失败:", error);
    }
  };

  // 处理模型切换
  const handleProviderChange = async (provider: string) => {
    // 切换到新的提供商
    setSelectedProvider(provider);

    // 加载新提供商的配置
    const newConfigId = getConfigIdByProvider(provider);
    if (newConfigId && modelConfigs[newConfigId]) {
      const config = { ...modelConfigs[newConfigId], enabled: true };
      setCurrentConfig(config);
      // 更新配置，将 enabled 设置为 true
      await videoModelService.updateConfig(newConfigId, config);
      // 重新加载配置以保持状态同步
      await loadVideoAnalysisConfigs();
    } else {
      // 如果没有缓存的配置，使用默认值
      const newConfig = {
        provider: provider,
        api_key: "",
        base_url: getDefaultBaseUrl(provider),
        model_name: getDefaultModelName(provider),
        extra_params: {},
        description: getDefaultDescription(provider),
        enabled: true,
      };
      setCurrentConfig(newConfig);
    }

    setTestResult(null);
  };

  // 更新当前配置并自动保存
  const updateCurrentConfig = async (field: string, value: any) => {
    const updatedConfig = {
      ...currentConfig,
      [field]: value,
    };
    setCurrentConfig(updatedConfig);

    // 自动保存配置
    await autoSaveVideoModelConfig(updatedConfig);
  };

  // 自动保存视频生成模型配置
  const autoSaveVideoModelConfig = async (config: VideoModelConfig) => {
    try {
      const configId = getConfigIdByProvider(config.provider);

      // 更新配置
      const response = await videoModelService.updateConfig(
        configId,
        config
      );

      if (response.success) {
        await loadVideoAnalysisConfigs();
      }
    } catch (error) {
      console.error("自动保存视频生成模型配置失败:", error);
      message.error("保存配置失败");
    }
  };

  // 测试连接
  const testModelConnection = async () => {
    try {
      setTestingConnection(true);
      setTestResult(null);

      const configId = getConfigIdByProvider(selectedProvider);
      const response = await videoModelService.testConnection(configId);

      if (response.success) {
        setTestResult({ success: true, message: "连接测试成功！" });
      } else {
        setTestResult({
          success: false,
          message: response.data?.error || "连接测试失败",
        });
      }
    } catch (error) {
      console.error("测试连接失败:", error);
      setTestResult({
        success: false,
        message: "连接测试失败：" + (error as Error).message,
      });
    } finally {
      setTestingConnection(false);
    }
  };

  return {
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
  };
};

