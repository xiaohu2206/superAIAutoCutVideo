import React from "react";
import { Box, Download, ShieldAlert, Copy, Check } from "lucide-react";
import type { Qwen3TtsDownloadProvider } from "../types";

type OptionItem = { id: string; label: string; keys: string[] };

type Status = { existsAll: boolean; validAll: boolean; missing: string[] };
type BadgeInfo = { className: string; text: string };
type DownloadInfo = { key: string; progress: number; message?: string } | null;

export type Qwen3ModelOptionsListProps = {
  options: OptionItem[];
  modelsLoading: boolean;
  modelsDownload: DownloadInfo;
  getModelStatus: (keys: string[]) => Status;
  getBadgeInfo: (status: Status) => BadgeInfo;
  getProvider: (optionId: string) => Qwen3TtsDownloadProvider;
  onChangeProvider: (optionId: string, provider: Qwen3TtsDownloadProvider) => void;
  onDownload: (option: OptionItem) => Promise<void> | void;
  onValidate: (option: OptionItem) => Promise<void> | void;
  onCopyPath: (option: OptionItem) => Promise<void> | void;
  copiedOptionId: string | null;
};

const Qwen3ModelOptionsList: React.FC<Qwen3ModelOptionsListProps> = ({
  options,
  modelsLoading,
  modelsDownload,
  getModelStatus,
  getBadgeInfo,
  getProvider,
  onChangeProvider,
  onDownload,
  onValidate,
  onCopyPath,
  copiedOptionId,
}) => {
  return (
    <div className="space-y-2">
      {options.map((option) => {
        const status = getModelStatus(option.keys);
        const badge = getBadgeInfo(status);
        const isDownloading = Boolean(modelsDownload) && option.keys.includes(modelsDownload!.key);

        return (
          <div
            key={option.id}
            className="bg-white border rounded-lg p-3 shadow-sm hover:shadow-md transition-shadow"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-start gap-3">
                <div
                  className={`p-2 rounded-lg ${
                    status.existsAll ? "bg-blue-50 text-blue-600" : "bg-gray-100 text-gray-500"
                  }`}
                >
                  <Box className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h5 className="text-sm font-medium text-gray-900">{option.label}</h5>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full border ${badge.className}`}
                      title={status.missing.length ? `缺失: ${status.missing.join(", ")}` : ""}
                    >
                      {badge.text}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">包含: {option.keys.join(", ")}</div>
                </div>
              </div>

              <div className="flex items-center gap-2 self-end sm:self-center">
                {!status.existsAll && (
                  <select
                    value={getProvider(option.id)}
                    onChange={(e) =>
                      onChangeProvider(option.id, e.target.value as Qwen3TtsDownloadProvider)
                    }
                    className="text-[11px] border rounded px-1.5 py-1 bg-gray-50 text-gray-600 h-7"
                    disabled={modelsLoading || Boolean(modelsDownload)}
                    title="下载源"
                  >
                    <option value="hf">HuggingFace</option>
                    <option value="modelscope">ModelScope</option>
                  </select>
                )}

                <div className="flex items-center border rounded-md overflow-hidden bg-white">
                  {!status.existsAll && (
                    <button
                      onClick={() => onDownload(option)}
                      disabled={modelsLoading || Boolean(modelsDownload)}
                      className="px-2.5 py-1 text-xs border-r hover:bg-gray-50 flex items-center gap-1.5 h-7 transition-colors text-blue-600 font-medium disabled:bg-gray-50 disabled:text-gray-400"
                      title="下载模型"
                    >
                      <Download className="h-3.5 w-3.5" />
                    </button>
                  )}

                  <button
                    onClick={() => onValidate(option)}
                    disabled={modelsLoading || Boolean(modelsDownload)}
                    className="px-2.5 py-1 text-xs border-r hover:bg-gray-50 text-gray-700 h-7 disabled:bg-gray-50 disabled:text-gray-400"
                    title="校验完整性"
                  >
                    <ShieldAlert className="h-3.5 w-3.5" />
                  </button>

                  <button
                    onClick={() => onCopyPath(option)}
                    disabled={modelsLoading || Boolean(modelsDownload)}
                    className="px-2.5 py-1 text-xs hover:bg-gray-50 text-gray-700 h-7 disabled:bg-gray-50 disabled:text-gray-400"
                    title="复制路径"
                  >
                    {copiedOptionId === option.id ? (
                      <Check className="h-3.5 w-3.5 text-green-600" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </div>
            </div>

            {isDownloading && (
              <div className="mt-3 pt-2 border-t border-gray-100">
                <div className="flex items-center justify-between text-[11px] text-gray-600 mb-1">
                  <span className="truncate">{modelsDownload?.message || "下载中…"}</span>
                  <span className="tabular-nums">{Math.round(modelsDownload?.progress || 0)}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
                  <div
                    className="h-full bg-blue-600 transition-all duration-300"
                    style={{
                      width: `${Math.max(
                        0,
                        Math.min(100, modelsDownload?.progress || 0)
                      )}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default Qwen3ModelOptionsList;
