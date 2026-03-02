import React from "react";
import { Box, Download, ShieldAlert, Copy, Check, Square, Info } from "lucide-react";
import type { FunAsrDownloadProvider } from "../types";
import FunAsrDownloadProgress from "./FunAsrDownloadProgress";

type OptionItem = { id: string; label: string; keys: string[]; description?: string };

type Status = { existsAll: boolean; validAll: boolean; missing: string[] };
type BadgeInfo = { className: string; text: string };
type DownloadInfo =
  | {
      key: string;
      progress: number;
      message?: string;
      status?: string;
      downloadedBytes?: number;
      totalBytes?: number | null;
      ownerOptionId?: string;
    }
  | null;

export type FunAsrModelOptionsListProps = {
  options: OptionItem[];
  modelsLoading: boolean;
  downloadsByKey: Record<string, DownloadInfo>;
  getModelStatus: (keys: string[]) => Status;
  getBadgeInfo: (status: Status) => BadgeInfo;
  getProvider: (optionId: string) => FunAsrDownloadProvider;
  onChangeProvider: (optionId: string, provider: FunAsrDownloadProvider) => void;
  onDownload: (option: OptionItem) => Promise<void> | void;
  onStop: (option: OptionItem) => Promise<void> | void;
  onValidate: (option: OptionItem) => Promise<void> | void;
  onOpenDir: (option: OptionItem) => Promise<void> | void;
  copiedOptionId: string | null;
};

const FunAsrModelOptionsList: React.FC<FunAsrModelOptionsListProps> = ({
  options,
  modelsLoading,
  downloadsByKey,
  getModelStatus,
  getBadgeInfo,
  getProvider,
  onChangeProvider,
  onDownload,
  onStop,
  onValidate,
  onOpenDir,
  copiedOptionId,
}) => {
  console.log("options222: ", options)
  const keyUsage = React.useMemo(() => {
    const usage: Record<string, string[]> = {};
    options.forEach((option) => {
      option.keys.forEach((key) => {
        if (!usage[key]) usage[key] = [];
        if (!usage[key].includes(option.id)) {
          usage[key].push(option.id);
        }
      });
    });
    return usage;
  }, [options]);
  return (
    <div className="space-y-4">
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800 flex gap-2">
        <Info className="w-5 h-5 flex-shrink-0 text-blue-600" />
        <div className="space-y-1">
          <p className="font-medium">模型选择说明：</p>
          <ul className="list-disc list-inside text-blue-700 space-y-0.5 ml-1">
            <li>每个选项包含 ASR 模型 + VAD 模型；两者都可用才算“就绪”。</li>
            <li>支持点击按钮在线下载，也支持手动下载后复制到对应目录再点“校验”。</li>
          </ul>
        </div>
      </div>

      <div className="space-y-2">
        {options.map((option) => {
          const status = getModelStatus(option.keys);
          const badge = getBadgeInfo(status);
          const activeDownloads = option.keys
            .map((key) => {
              const download = downloadsByKey[key];
              if (!download) return null;
              const owners = keyUsage[key] || [];
              if (download.ownerOptionId) {
                return download.ownerOptionId === option.id ? download : null;
              }
              if (owners.length <= 1) return download;
              return owners[0] === option.id ? download : null;
            })
            .filter(Boolean) as DownloadInfo[];
          const isDownloading = activeDownloads.length > 0;
          const currentDownload = activeDownloads[0];
          const canStop = currentDownload?.status === "running";

          return (
            <div key={option.id} className="bg-white border rounded-lg p-3 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-lg ${status.existsAll ? "bg-blue-50 text-blue-600" : "bg-gray-100 text-gray-500"}`}>
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
                    {option.description ? <div className="mt-1 text-xs text-gray-500">{option.description}</div> : null}
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-center">
                  {!status.validAll && (
                    <select
                      value={getProvider(option.id)}
                      onChange={(e) => onChangeProvider(option.id, e.target.value as FunAsrDownloadProvider)}
                      className="text-[11px] border rounded px-1.5 py-1 bg-gray-50 text-gray-600 h-7"
                      disabled={modelsLoading || isDownloading}
                      title="下载源"
                    >
                      <option value="modelscope">国内（ModelScope）</option>
                      <option value="hf">国外（HuggingFace）</option>
                    </select>
                  )}

                  <div className="flex items-center border rounded-md overflow-hidden bg-white">
                    {!status.validAll && (
                      <button
                        onClick={() => onDownload(option)}
                        disabled={modelsLoading || isDownloading}
                        className="px-2.5 py-1 text-xs border-r hover:bg-gray-50 flex items-center gap-1.5 h-7 transition-colors text-blue-600 font-medium disabled:bg-gray-50 disabled:text-gray-400"
                        title="下载模型"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </button>
                    )}

                    {isDownloading && (
                      <button
                        onClick={() => onStop(option)}
                        disabled={modelsLoading || !canStop}
                        className="px-2.5 py-1 text-xs border-r hover:bg-gray-50 flex items-center gap-1.5 h-7 transition-colors text-red-600 font-medium disabled:bg-gray-50 disabled:text-gray-400"
                        title="停止下载"
                      >
                        <Square className="h-3.5 w-3.5" />
                      </button>
                    )}

                    <button
                      onClick={() => onValidate(option)}
                      disabled={modelsLoading || isDownloading}
                      className="px-2.5 py-1 text-xs border-r hover:bg-gray-50 text-gray-700 h-7 disabled:bg-gray-50 disabled:text-gray-400"
                      title="校验完整性"
                    >
                      <ShieldAlert className="h-3.5 w-3.5" />
                    </button>

                    <button
                      onClick={() => onOpenDir(option)}
                      disabled={modelsLoading || isDownloading}
                      className="px-2.5 py-1 text-xs hover:bg-gray-50 text-gray-700 h-7 disabled:bg-gray-50 disabled:text-gray-400"
                      title="打开模型目录"
                    >
                      {copiedOptionId === option.id ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
                    </button>
                  </div>
                </div>
              </div>

              <FunAsrDownloadProgress download={currentDownload} />
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default FunAsrModelOptionsList;
