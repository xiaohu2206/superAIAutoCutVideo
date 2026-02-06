import React from "react";
import { Download, HardDrive } from "lucide-react";

type DownloadInfo = {
  key: string;
  progress: number;
  message?: string;
  status?: string;
  downloadedBytes?: number;
  totalBytes?: number | null;
} | null;

export type FunAsrDownloadProgressProps = {
  download: DownloadInfo;
};

export const FunAsrDownloadProgress: React.FC<FunAsrDownloadProgressProps> = ({ download }) => {
  if (!download) return null;

  const { progress, message, downloadedBytes, totalBytes } = download;
  const p = Math.max(0, Math.min(100, progress || 0));

  const formatSizeM = (bytes?: number | string | null) => {
    if (bytes === null || bytes === undefined) return "--";
    const val = Number(bytes);
    if (Number.isNaN(val)) return "--";
    const mb = Math.max(0, val) / (1024 * 1024);
    return `${mb.toFixed(1)}M`;
  };

  const sizeText = `${formatSizeM(downloadedBytes)} / ${formatSizeM(totalBytes)}`;

  return (
    <div className="mt-3 bg-blue-50/50 rounded-lg p-3 border border-blue-100">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-100 text-blue-600 rounded-md animate-pulse">
            <Download className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-medium text-blue-900 truncate max-w-[180px]" title={message || "下载中..."}>
            {message || "下载中..."}
          </span>
        </div>
        <span className="text-xs font-bold text-blue-700 tabular-nums">{Math.round(p)}%</span>
      </div>

      <div className="h-1.5 w-full bg-blue-200 rounded-full overflow-hidden mb-2">
        <div className="h-full bg-blue-600 rounded-full transition-all duration-300 ease-out relative overflow-hidden" style={{ width: `${p}%` }}>
          <div
            className="absolute inset-0 w-full h-full animate-shimmer"
            style={{
              backgroundImage: "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.3) 50%, transparent 100%)",
              backgroundSize: "200% 100%",
            }}
          />
        </div>
      </div>

      <div className="flex items-center justify-between text-[10px] text-blue-400">
        <div className="flex items-center gap-1">
          <HardDrive className="w-3 h-3" />
          <span>下载数据</span>
        </div>
        <span className="tabular-nums font-medium">{sizeText}</span>
      </div>
    </div>
  );
};

export default FunAsrDownloadProgress;

