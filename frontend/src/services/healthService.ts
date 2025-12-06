import { apiClient } from "./clients";

export interface IntegrationTestResult {
  content_model: {
    status: "ok" | "error" | "unknown";
    message: string;
    details?: any;
  };
  tts: {
    status: "ok" | "error" | "unknown";
    message: string;
    details?: any;
  };
  asr: {
    status: "ok" | "error" | "unknown";
    message: string;
    details?: any;
  };
  overall_status: "healthy" | "unhealthy";
}

export const healthService = {
  /**
   * 一键测试所有集成组件
   */
  testIntegrations: () => apiClient.testIntegrations(),
};

export default healthService;
