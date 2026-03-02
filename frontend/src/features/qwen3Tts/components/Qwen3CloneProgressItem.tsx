import React from "react";

export type Qwen3CloneProgressItemProps = {
  progress: number;
  message?: string;
  phase?: string;
  type?: string;
};

export const Qwen3CloneProgressItem: React.FC<Qwen3CloneProgressItemProps> = ({ progress, message: msg, phase, type }) => {
  const p = Math.max(0, Math.min(100, Number.isFinite(progress) ? progress : 0));
  const label = msg || phase || (type === "completed" ? "完成" : type === "error" ? "失败" : "处理中");

  return (
    <div className="w-full">
      <div className="flex items-center justify-between gap-2 text-xs text-gray-600">
        <span className="truncate">{label}</span>
        <span className="flex-shrink-0 tabular-nums">{p}%</span>
      </div>
      <div className="mt-1 h-2 w-full rounded bg-gray-100 overflow-hidden">
        <div className="h-full bg-blue-600 transition-all" style={{ width: `${p}%` }} />
      </div>
    </div>
  );
};

export default Qwen3CloneProgressItem;

