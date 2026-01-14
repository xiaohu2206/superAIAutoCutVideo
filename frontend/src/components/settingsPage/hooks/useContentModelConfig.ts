import { useEffect, useState } from "react";
import { contentModelService } from "../../../services/contentModelService";
import { message } from "../../../services/message";
import type { ContentModelConfig, TestResult } from "../types";
import {
    getContentConfigIdByProvider,
    getContentDefaultBaseUrl,
    getContentDefaultDescription,
    getContentDefaultModelName,
} from "../utils";

/**
 * 文案生成模型配置管理 Hook
 */
export const useContentModelConfig = () => {
  const [contentSelectedProvider, setContentSelectedProvider] =
    useState<string>("qwen");
  const [contentModelConfigs, setContentModelConfigs] = useState<
    Record<string, ContentModelConfig>
  >({});
  const [currentContentConfig, setCurrentContentConfig] =
    useState<ContentModelConfig>({
      provider: "qwen",
      api_key: "",
      base_url: "",
      model_name: "",
      extra_params: {},
      description: "",
    });
  const [testingContentConnection, setTestingContentConnection] = useState(false);
  const [contentTestResult, setContentTestResult] = useState<TestResult | null>(null);
  const [contentTestStructured, setContentTestStructured] = useState<string | null>(null);
  const [showContentPassword, setShowContentPassword] = useState(false);

  useEffect(() => {
    loadContentGenerationConfigs();
  }, []);

  const loadContentGenerationConfigs = async () => {
    try {
      const response = await contentModelService.getConfigs();
      if (response.success) {
        const configs = response.data.configs;
        setContentModelConfigs(configs);

        // 使用 enabled 为 true 的配置作为当前配置
        if (Object.keys(configs).length > 0) {
          // 查找 enabled 为 true 的配置
          const enabledConfigId = Object.keys(configs).find(
            (id) => configs[id].enabled === true
          );

          // 如果找到启用的配置，使用它；否则使用第一个配置
          const activeConfigId = enabledConfigId || Object.keys(configs)[0];
          const activeConfig = configs[activeConfigId];
          setContentSelectedProvider(activeConfig.provider);
          setCurrentContentConfig(activeConfig);
        }
      }
    } catch (error) {
      console.error("加载文案生成模型配置失败:", error);
    }
  };

  // 处理文案生成模型切换
  const handleContentProviderChange = async (provider: string) => {
    // 切换到新的提供商
    setContentSelectedProvider(provider);

    // 加载新提供商的配置
    const newConfigId = getContentConfigIdByProvider(provider);
    if (newConfigId && contentModelConfigs[newConfigId]) {
      const config = { ...contentModelConfigs[newConfigId], enabled: true };
      setCurrentContentConfig(config);
      // 更新配置，将 enabled 设置为 true
      await contentModelService.updateConfig(newConfigId, config);
      // 重新加载配置以保持状态同步
      await loadContentGenerationConfigs();
    } else {
      // 如果没有缓存的配置，使用默认值
      const newConfig = {
        provider: provider,
        api_key: "",
        base_url: getContentDefaultBaseUrl(provider),
        model_name: getContentDefaultModelName(provider),
        extra_params: {},
        description: getContentDefaultDescription(provider),
        enabled: true,
      };
      setCurrentContentConfig(newConfig);
    }

    setContentTestResult(null);
  };

  // 更新当前文案生成模型配置并自动保存
  const updateCurrentContentConfig = async (field: string, value: any) => {
    const updatedConfig = {
      ...currentContentConfig,
      [field]: value,
    };
    setCurrentContentConfig(updatedConfig);

    // 自动保存配置
    await autoSaveContentModelConfig(updatedConfig);
  };

  // 自动保存文案生成模型配置
  const autoSaveContentModelConfig = async (config: ContentModelConfig) => {
    try {
      const configId = getContentConfigIdByProvider(config.provider);

      // 更新配置
      const response = await contentModelService.updateConfig(
        configId,
        config
      );

      if (response.success) {
        await loadContentGenerationConfigs();
      }
    } catch (error) {
      console.error("自动保存文案生成模型配置失败:", error);
      message.error("保存配置失败");
    }
  };

  // 测试文案生成模型连接
  const testContentModelConnection = async () => {
    try {
      setTestingContentConnection(true);
      setContentTestResult(null);
      setContentTestStructured(null);

      const configId = getContentConfigIdByProvider(contentSelectedProvider);
      const response = await contentModelService.testConnection(configId);

      if (response.success) {
        const structured =
          response.data?.structured_output ??
          null;
        const raw =
          response.data?.raw_content ??
          response.data?.response_preview ??
          null;
        setContentTestResult({ success: true, message: "连接测试成功！" });
        if (structured) {
          try {
            setContentTestStructured(JSON.stringify(structured, null, 2));
          } catch {
            setContentTestStructured(String(structured));
          }
        } else if (raw) {
          setContentTestStructured(String(raw));
        } else {
          setContentTestStructured(null);
        }
      } else {
        setContentTestResult({
          success: false,
          message: response.data?.error || "连接测试失败",
        });
        setContentTestStructured(
          response.data?.raw_content || response.data?.response_preview || null
        );
      }
    } catch (error) {
      console.error("测试文案生成模型连接失败:", error);
      setContentTestResult({
        success: false,
        message: "连接测试失败：" + (error as Error).message,
      });
      setContentTestStructured(null);
    } finally {
      setTestingContentConnection(false);
    }
  };

  return {
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
  };
};

