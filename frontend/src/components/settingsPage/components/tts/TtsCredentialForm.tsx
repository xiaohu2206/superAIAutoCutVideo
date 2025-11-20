import { KeyRound, Loader, ShieldAlert, ShieldCheck } from "lucide-react";
import React, { useEffect, useState } from "react";
import type { TtsEngineConfig, TtsTestResult } from "../../types";

interface Props {
  configId: string | null;
  config?: TtsEngineConfig;
  hasCredentials: boolean;
  onUpdate: (partial: Partial<TtsEngineConfig>) => Promise<void> | void;
  onTest: () => Promise<void> | void;
  testing: boolean;
  testDurationMs: number | null;
  testResult: TtsTestResult | null;
  activeConfigId: string | null;
}

export const TtsCredentialForm: React.FC<Props> = ({
  configId,
  config,
  hasCredentials,
  onUpdate,
  onTest,
  testing,
  testDurationMs,
  testResult,
  activeConfigId,
}) => {
  void activeConfigId;
  const [secretIdInput, setSecretIdInput] = useState<string>("");
  const [secretKeyInput, setSecretKeyInput] = useState<string>("");

  useEffect(() => {
    // 初始不展示敏感值，仅提示设置状态
    setSecretIdInput("");
    setSecretKeyInput("");
  }, [configId]);

  const handleBlurSecretId = async () => {
    const trimmed = secretIdInput.trim();
    if (!trimmed) return;
    await onUpdate({ secret_id: trimmed });
    setSecretIdInput("");
  };

  const handleBlurSecretKey = async () => {
    const trimmed = secretKeyInput.trim();
    if (!trimmed) return;
    await onUpdate({ secret_key: trimmed });
    setSecretKeyInput("");
  };

  return (
    <div>
      <h4 className="text-md font-semibold text-gray-900 mb-2">凭据设置</h4>
      <p className="text-gray-600 text-sm mb-4">
        为保障安全，凭据仅展示设置状态，不显示明文。
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-700 mb-1">SecretId</label>
          <div className="flex items-center gap-2">
            <input
              type="password"
              value={secretIdInput}
              placeholder={config?.secret_id === "***" ? "已设置" : "未设置"}
              onChange={(e) => setSecretIdInput(e.target.value)}
              onBlur={handleBlurSecretId}
              className="px-3 py-2 border border-gray-300 rounded-md w-full"
            />
            {config?.secret_id === "***" ? (
              <ShieldCheck className="h-5 w-5 text-green-600" />
            ) : (
              <ShieldAlert className="h-5 w-5 text-orange-600" />
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm text-gray-700 mb-1">SecretKey</label>
          <div className="flex items-center gap-2">
            <input
              type="password"
              value={secretKeyInput}
              placeholder={config?.secret_key === "***" ? "已设置" : "未设置"}
              onChange={(e) => setSecretKeyInput(e.target.value)}
              onBlur={handleBlurSecretKey}
              className="px-3 py-2 border border-gray-300 rounded-md w-full"
            />
            {config?.secret_key === "***" ? (
              <ShieldCheck className="h-5 w-5 text-green-600" />
            ) : (
              <ShieldAlert className="h-5 w-5 text-orange-600" />
            )}
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          className={`inline-flex items-center px-3 py-2 rounded-md text-sm ${
            testing || !hasCredentials || !configId
              ? "bg-gray-200 text-gray-500 cursor-not-allowed"
              : "bg-gray-100 hover:bg-gray-200 text-gray-800"
          }`}
          onClick={() => onTest()}
          disabled={testing || !hasCredentials || !configId}
          title={hasCredentials ? "测试连通性" : "请先填写并保存 SecretId/SecretKey"}
        >
          {testing ? <Loader className="h-4 w-4 mr-1 animate-spin" /> : <KeyRound className="h-4 w-4 mr-1" />}
          测试连通性
        </button>

        {testResult && (
          <div className={`inline-flex items-center text-sm ${testResult.success ? "text-green-600" : "text-red-600"}`}>
            {testResult.success ? <ShieldCheck className="h-4 w-4 mr-1" /> : <ShieldAlert className="h-4 w-4 mr-1" />}
            {testResult.success
              ? `已连接腾讯云 TTS（响应 ${testDurationMs ?? "--"}ms）`
              : `鉴权失败，请检查 SecretId/SecretKey`}
          </div>
        )}
      </div>
    </div>
  );
};

export default TtsCredentialForm;