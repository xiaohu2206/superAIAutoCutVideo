import { useCallback, useEffect, useRef, useState } from "react";
import { message } from "@/services/message";
import aiSearchShotSettingsService from "@/services/aiSearchShotSettingsService";
import type { AiSearchShotModelConfig, TestResult } from "../types";

const DEFAULT_CONFIG: AiSearchShotModelConfig = {
  provider: "yunwu",
  api_key: "",
  embedding_base_url: "https://yunwu.ai/v1/embeddings",
  embedding_model: "gemini-embedding-2-preview",
  rerank_base_url: "https://yunwu.ai/v1/rerank",
  rerank_model: "qwen3-rerank",
  timeout_seconds: 300,
  max_retries: 5,
  retry_sleep_seconds: 2,
  enabled: true,
  description: "向量模型 向量与召回模型配置（当前仅支持云雾）",
};

export const useAiSearchShotModelConfig = () => {
  const [config, setConfig] = useState<AiSearchShotModelConfig>(DEFAULT_CONFIG);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingEmbedding, setTestingEmbedding] = useState(false);
  const [testingRerank, setTestingRerank] = useState(false);
  const [embeddingTestResult, setEmbeddingTestResult] = useState<TestResult | null>(null);
  const [rerankTestResult, setRerankTestResult] = useState<TestResult | null>(null);
  const [embeddingTestDetail, setEmbeddingTestDetail] = useState<string | null>(null);
  const [rerankTestDetail, setRerankTestDetail] = useState<string | null>(null);

  const configRef = useRef<AiSearchShotModelConfig>(DEFAULT_CONFIG);

  useEffect(() => {
    configRef.current = config;
  }, [config]);

  const loadConfig = useCallback(async () => {
    try {
      setLoading(true);
      const response = await aiSearchShotSettingsService.getConfig();
      const nextConfig = response?.data?.config;
      if (nextConfig) {
        setConfig({
          ...DEFAULT_CONFIG,
          ...nextConfig,
        });
      }
    } catch (error) {
      console.error("加载 向量模型 模型配置失败:", error);
      message.error("加载 向量模型 模型配置失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConfig();
  }, [loadConfig]);

  const saveConfig = useCallback(async (nextConfig: AiSearchShotModelConfig) => {
    try {
      setSaving(true);
      const response = await aiSearchShotSettingsService.updateConfig(nextConfig);
      const saved = response?.data?.config;
      if (saved) {
        setConfig({
          ...DEFAULT_CONFIG,
          ...saved,
        });
      }
      message.success("向量模型 模型配置已保存");
    } catch (error: any) {
      console.error("保存 向量模型 模型配置失败:", error);
      message.error(error?.message || "保存 向量模型 模型配置失败");
      throw error;
    } finally {
      setSaving(false);
    }
  }, []);

  const updateField = useCallback(
    (field: keyof AiSearchShotModelConfig, value: string | number | boolean) => {
      setConfig((prev) => ({
        ...prev,
        [field]: value,
      }));
    },
    []
  );

  const testEmbedding = useCallback(async () => {
    try {
      setTestingEmbedding(true);
      setEmbeddingTestResult(null);
      setEmbeddingTestDetail(null);
      const response = await aiSearchShotSettingsService.testEmbedding(configRef.current);
      const result = response?.data;
      if (response?.success && result?.success) {
        setEmbeddingTestResult({ success: true, message: result.message || "向量模型测试成功" });
        setEmbeddingTestDetail(JSON.stringify(result, null, 2));
      } else {
        setEmbeddingTestResult({
          success: false,
          message: result?.message || response?.message || "向量模型测试失败",
        });
        setEmbeddingTestDetail(result ? JSON.stringify(result, null, 2) : null);
      }
    } catch (error: any) {
      console.error("测试向量模型失败:", error);
      setEmbeddingTestResult({ success: false, message: error?.message || "向量模型测试失败" });
      setEmbeddingTestDetail(null);
    } finally {
      setTestingEmbedding(false);
    }
  }, []);

  const testRerank = useCallback(async () => {
    try {
      setTestingRerank(true);
      setRerankTestResult(null);
      setRerankTestDetail(null);
      const response = await aiSearchShotSettingsService.testRerank(configRef.current);
      const result = response?.data;
      if (response?.success && result?.success) {
        setRerankTestResult({ success: true, message: result.message || "召回模型测试成功" });
        setRerankTestDetail(JSON.stringify(result, null, 2));
      } else {
        setRerankTestResult({
          success: false,
          message: result?.message || response?.message || "召回模型测试失败",
        });
        setRerankTestDetail(result ? JSON.stringify(result, null, 2) : null);
      }
    } catch (error: any) {
      console.error("测试召回模型失败:", error);
      setRerankTestResult({ success: false, message: error?.message || "召回模型测试失败" });
      setRerankTestDetail(null);
    } finally {
      setTestingRerank(false);
    }
  }, []);

  return {
    config,
    setConfig,
    configRef,
    loading,
    saving,
    loadConfig,
    saveConfig,
    updateField,
    testingEmbedding,
    testingRerank,
    embeddingTestResult,
    rerankTestResult,
    embeddingTestDetail,
    rerankTestDetail,
    testEmbedding,
    testRerank,
  };
};

export default useAiSearchShotModelConfig;
