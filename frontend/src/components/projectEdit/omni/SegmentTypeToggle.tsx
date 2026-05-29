import { Mic2, Repeat2, Volume2 } from "lucide-react";
import React from "react";
import { useThemeMode } from "../../../hooks/useThemeMode";

export interface SegmentTypeToggleProps {
  original: boolean;
  disabled?: boolean;
  title?: string;
  onToggle: () => void;
}

export const SegmentTypeToggle: React.FC<SegmentTypeToggleProps> = ({
  original,
  disabled,
  title,
  onToggle,
}) => {
  const isDark = useThemeMode() === "dark";

  const variantClass = original
    ? isDark
      ? "border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20"
      : "border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100"
    : isDark
      ? "border-blue-500/40 bg-blue-500/10 text-blue-300 hover:bg-blue-500/20"
      : "border-blue-300 bg-blue-50 text-blue-900 hover:bg-blue-100";

  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onToggle}
      title={title || (original ? "切换为解说镜头" : "切换为原片播放")}
      className={`group w-full flex items-center justify-center gap-0.5 px-1 py-1 rounded-md text-[10px] font-medium border cursor-pointer transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100 ${
        isDark ? "" : "shadow-sm hover:shadow-md disabled:hover:shadow-sm"
      } ${variantClass}`}
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
};

export default SegmentTypeToggle;
