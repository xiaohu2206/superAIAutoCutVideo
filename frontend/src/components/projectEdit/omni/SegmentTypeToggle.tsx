import { Mic2, Repeat2, Volume2 } from "lucide-react";
import React from "react";

export interface SegmentTypeToggleProps {
  original: boolean;
  disabled?: boolean;
  title?: string;
  onToggle: () => void;
}

const SegmentTypeToggle: React.FC<SegmentTypeToggleProps> = ({
  original,
  disabled,
  title,
  onToggle,
}) => (
  <button
    type="button"
    disabled={disabled}
    onClick={onToggle}
    title={title || (original ? "切换为解说镜头" : "切换为原片播放")}
    className={`group w-full flex items-center justify-center gap-0.5 px-1 py-1 rounded-md text-[10px] font-medium border shadow-sm cursor-pointer transition-all hover:shadow-md active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-sm disabled:active:scale-100 ${
      original
        ? "border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100 dark:border-amber-600/80 dark:bg-amber-950/50 dark:text-amber-200 dark:hover:bg-amber-900/60"
        : "border-blue-300 bg-blue-50 text-blue-900 hover:bg-blue-100 dark:border-blue-600/80 dark:bg-blue-950/50 dark:text-blue-200 dark:hover:bg-blue-900/60"
    }`}
  >
    {original ? (
      <Volume2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
    ) : (
      <Mic2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
    )}
    <span className="leading-none">{original ? "原片播放" : "解说镜头"}</span>
    <Repeat2 className="h-3 w-3 shrink-0 opacity-50 group-hover:opacity-100" aria-hidden />
  </button>
);

export default SegmentTypeToggle;
