import React from "react";
import { Box, Download, ShieldAlert, Copy, Check, Square, Info } from "lucide-react";
import type { VoxcpmTtsDownloadProvider } from "../types";
import VoxcpmCloneProgressItem from "./VoxcpmCloneProgressItem";
import { TauriCommands } from "@/services/clients";

type OptionItem = { id: string; label: string; keys: string[]; size?: string; description?: string };

type Status = { existsAll: boolean; validAll: boolean; missing: string[] };
type BadgeInfo = { className: string; text: string };
type DownloadInfo = { key: string; progress: number; message?: string; status?: string; phase?: string; type?: string; downloadedBytes?: number; totalBytes?: number | null } | null;

export type VoxcpmModelOptionsListProps = {
  options: OptionItem[];
  modelsLoading: boolean;
  downloadsByKey: Record<string, DownloadInfo>;
  getModelStatus: (keys: string[]) => Status;
  getBadgeInfo: (status: Status) => BadgeInfo;
  getProvider: (optionId: string) => VoxcpmTtsDownloadProvider;
  onChangeProvider: (optionId: string, provider: VoxcpmTtsDownloadProvider) => void;
  onDownload: (option: OptionItem) => Promise<void> | void;
  onStop: (option: OptionItem) => Promise<void> | void;
  onValidate: (option: OptionItem) => Promise<void> | void;
  onOpenDir: (option: OptionItem) => Promise<void> | void;
  copiedOptionId: string | null;
};

const VoxcpmModelOptionsList: React.FC<VoxcpmModelOptionsListProps> = ({
  options,
  modelsLoading,
  downloadsByKey,
  getModelStatus,
  getBadgeInfo,
  onDownload,
  onStop,
  onValidate,
  onOpenDir,
  copiedOptionId,
}) => {
  return (
    <div className="space-y-4">
      <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 text-sm text-orange-800 flex gap-2">
        <Info className="w-5 h-5 flex-shrink-0 text-orange-600" />
        <div className="space-y-1">
          <p className="font-medium">模型下载说明：</p>
          <ul className="list-disc list-inside text-orange-700 space-y-0.5 ml-1">
            <li>下列模型只需<span className="font-bold">选择一个</span>下载即可使用。</li>
            <li>支持点击按钮在线下载，也支持手动下载后复制到对应目录(\uploads\models\OpenBMB\VoxCPM)。</li>
            <li>
                                                    手动下载入口：
                                                    <button 
                                                        onClick={() => TauriCommands.openExternalLink("https://my.feishu.cn/wiki/NI0qwbHftith0kkxhHJcjGlJnRc")}
                                                        className="ml-1 inline-flex items-center bg-transparent border-none cursor-pointer p-0 text-blue-700 underline hover:text-blue-900"
                                                        type="button"
                                                    >
                                                        网盘下载
                                                    </button>
                                                </li>
          </ul>
        </div>
      </div>

      <div className="space-y-2">
        {options.map((option) => {
          const status = getModelStatus(option.keys);
          const badge = getBadgeInfo(status);
          const activeDownloads = option.keys.map((k) => downloadsByKey[k]).filter(Boolean) as DownloadInfo[];
          const isDownloading = activeDownloads.length > 0;
          const currentDownload = activeDownloads[0];
          const canStop = currentDownload?.status === "running";

          return (
            <div
              key={option.id}
              className="bg-white border rounded-lg p-3 shadow-sm hover:shadow-md transition-shadow"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-start gap-3">
                  <div
                    className={`p-2 rounded-lg ${
                      status.existsAll ? "bg-orange-50 text-orange-600" : "bg-gray-100 text-gray-500"
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
                    {(option.size || option.description) && (
                      <div className="mt-1 flex flex-col gap-0.5 text-xs text-gray-500">
                        {option.size && (
                          <span className="flex items-center gap-1">
                            <span className="font-medium text-gray-600">大小:</span> {option.size}
                          </span>
                        )}
                        {option.description && (
                          <span className="text-gray-500">{option.description}</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-center">
                  <div className="flex items-center border rounded-md overflow-hidden bg-white">
                    {!status.validAll && (
                      <button
                        onClick={() => onDownload(option)}
                        disabled={modelsLoading || isDownloading}
                        className="px-2.5 py-1 text-xs border-r hover:bg-gray-50 flex items-center gap-1.5 h-7 transition-colors text-orange-600 font-medium disabled:bg-gray-50 disabled:text-gray-400"
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
                      校验
                    </button>

                    <button
                      onClick={() => onOpenDir(option)}
                      disabled={modelsLoading || isDownloading}
                      className="px-2.5 py-1 text-xs hover:bg-gray-50 text-gray-700 h-7 disabled:bg-gray-50 disabled:text-gray-400"
                      title="打开模型目录"
                    >
                      {copiedOptionId === option.id ? (
                        <Check className="h-3.5 w-3.5 text-green-600" />
                      ) : (
                        "目录"
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {currentDownload && (
                <VoxcpmCloneProgressItem
                  progress={currentDownload.progress || 0}
                  message={currentDownload.message}
                  phase={currentDownload.phase}
                  type={currentDownload.type}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default VoxcpmModelOptionsList;
