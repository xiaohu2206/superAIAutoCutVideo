import { AlertCircle, Loader } from "lucide-react";
import React from "react";
import type { WsProgressLog } from "../../../hooks/useWsTaskProgress";

export interface OmniFullNarrationPipelineProgressProps {
  busy: boolean;
  progress: number;
  logs: WsProgressLog[];
}

/**
 * 全链路进度条：布局与 ProjectOperations 中「脚本生成进度」块一致（w-full ml-0 mt-3），单独占一行全宽。
 */
const OmniFullNarrationPipelineProgress: React.FC<OmniFullNarrationPipelineProgressProps> = ({
  busy,
  progress,
  logs,
}) => {
  if (!busy && !(progress > 0 && progress < 100)) return null;

  return (
    <div className="w-full ml-0 mt-3">
      <div className="flex items-center justify-between text-xs text-gray-600 mb-1">
        <span>Omni 全链路进度（结构化 → 镜头 → 路径 → 脚本）</span>
        <span>{Math.round(progress)}%</span>
      </div>
      <div className="w-full h-2 mb-2 bg-gray-200 rounded">
        <div
          className="h-2 bg-violet-600 rounded transition-all"
          style={{ width: `${Math.round(progress)}%` }}
        />
      </div>
      {logs.length > 0 && (
        <div className="mb-2 space-y-1">
          {logs.slice(-1).map((log, idx) => (
            <div key={`${log.timestamp}-${idx}`} className="text-xs text-gray-700 flex items-center">
              {log.type === "error" ? (
                <AlertCircle className="h-3 w-3 mr-1 text-red-600" />
              ) : (
                <Loader className="h-3 w-3 mr-1 text-violet-600" />
              )}
              <span className="break-all">{log.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default OmniFullNarrationPipelineProgress;
