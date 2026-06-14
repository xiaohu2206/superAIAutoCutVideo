import React, { useCallback, useEffect, useRef, useState } from "react";
import { useThemeMode } from "../../../hooks/useThemeMode";

interface Props {
  copywritingWordCount: number | null;
  loading: boolean;
  saving: boolean;
  setCopywritingWordCountAndPersist: (value: number | null) => Promise<void>;
}

const MIN_COUNT = 50;
const MAX_COUNT = 50000;
const STEP = 50;
const MARKS = [MIN_COUNT, 5000, 15000, 20000, 30000, 35000, 45000, MAX_COUNT];

type SelectionMode = "wordCount" | "duration";

const DURATION_OPTIONS = [
  { label: "1~4 分钟", wordCount: 500 },
  { label: "3~7 分钟", wordCount: 1000 },
  { label: "5~10 分钟", wordCount: 1500 },
  { label: "8~15 分钟", wordCount: 2300 },
  { label: "12~20 分钟", wordCount: 3200 },
  { label: "18~30 分钟", wordCount: 4800 },
  { label: "25~40 分钟", wordCount: 6500 },
] as const;

const CopywritingWordCountSelector: React.FC<Props> = ({
  copywritingWordCount,
  loading,
  saving,
  setCopywritingWordCountAndPersist,
}) => {
  const isDark = useThemeMode() === "dark";
  const isAuto = copywritingWordCount === null || copywritingWordCount === undefined;
  const sliderValue = isAuto ? 0 : Math.max(MIN_COUNT, Math.min(MAX_COUNT, copywritingWordCount));

  const [inputValue, setInputValue] = useState<string>(isAuto ? "" : String(sliderValue));
  const [selectionMode, setSelectionMode] = useState<SelectionMode>("wordCount");
  const [selectedDurationWordCount, setSelectedDurationWordCount] = useState<number | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setInputValue(isAuto ? "" : String(sliderValue));
  }, [isAuto, sliderValue]);

  useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    []
  );

  const persistDebounced = useCallback(
    (val: number | null) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        void setCopywritingWordCountAndPersist(val);
      }, 400);
    },
    [setCopywritingWordCountAndPersist]
  );

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = parseInt(e.target.value, 10);
    if (raw <= 0) {
      setInputValue("");
      persistDebounced(null);
      return;
    }
    const clamped = Math.max(MIN_COUNT, Math.min(MAX_COUNT, Math.round(raw / STEP) * STEP));
    setInputValue(String(clamped));
    persistDebounced(clamped);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value.replace(/[^\d]/g, "");
    setInputValue(raw);
    if (!raw) {
      persistDebounced(null);
      return;
    }
    const num = parseInt(raw, 10);
    if (!isNaN(num) && num >= MIN_COUNT && num <= MAX_COUNT) {
      persistDebounced(num);
    }
  };

  const handleInputBlur = () => {
    if (!inputValue) {
      persistDebounced(null);
      return;
    }
    const num = parseInt(inputValue, 10);
    if (isNaN(num) || num < MIN_COUNT) {
      setInputValue("");
      persistDebounced(null);
    } else {
      const clamped = Math.min(MAX_COUNT, num);
      setInputValue(String(clamped));
      void setCopywritingWordCountAndPersist(clamped);
    }
  };

  const handleAutoClick = () => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setInputValue("");
    setSelectedDurationWordCount(null);
    void setCopywritingWordCountAndPersist(null);
  };

  const handleModeChange = (mode: SelectionMode) => {
    setSelectionMode(mode);
    if (mode === "duration") {
      const matchedOption = DURATION_OPTIONS.find((option) => option.wordCount === copywritingWordCount);
      setSelectedDurationWordCount(matchedOption?.wordCount ?? null);
    }
  };

  const handleDurationSelect = (wordCount: number) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setSelectedDurationWordCount(wordCount);
    setInputValue(String(wordCount));
    void setCopywritingWordCountAndPersist(wordCount);
  };

  return (
    <div className={`border-t pt-4 ${isDark ? "border-[#2a2a2a]" : "border-gray-200"}`}>
      <div className="flex items-center justify-between mb-3">
        <label className={`block text-sm font-medium ${isDark ? "text-zinc-200" : "text-gray-700"}`}>
          解说文案字数
          <span className={`text-xs ${isDark ? "text-zinc-500" : "text-gray-400"}`}>
            （可按字数或预计视频时长设置）
          </span>
        </label>
        {loading ? (
          <span className={`text-xs ${isDark ? "text-zinc-400" : "text-gray-500"}`}>加载中</span>
        ) : saving ? (
          <span className={`text-xs ${isDark ? "text-zinc-400" : "text-gray-500"}`}>保存中</span>
        ) : (
          <span className={`text-xs ${isDark ? "text-zinc-400" : "text-gray-500"}`}>
            {isAuto ? "自动（由模型决定）" : `目标 ${sliderValue.toLocaleString()} 字`}
          </span>
        )}
      </div>

      <div
        className={`inline-flex rounded-lg p-1 mb-3 ${isDark ? "bg-[#242424]" : "bg-gray-100"}`}
        role="group"
        aria-label="文案长度设置方式"
      >
        {([
          { value: "wordCount", label: "按字数" },
          { value: "duration", label: "按视频时长" },
        ] as const).map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => handleModeChange(option.value)}
            aria-pressed={selectionMode === option.value}
            className={`px-3 py-1.5 text-xs rounded-md transition-all duration-200 ${
              selectionMode === option.value
                ? isDark
                  ? "bg-violet-500/15 text-violet-300 shadow-sm"
                  : "bg-white text-violet-700 shadow-sm"
                : isDark
                  ? "text-zinc-400 hover:text-zinc-200"
                  : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      {selectionMode === "wordCount" ? (
        <>
          <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleAutoClick}
          className={`
            shrink-0 px-3 py-1.5 text-xs rounded-md border transition-all duration-200
            ${
              isAuto
                ? isDark
                  ? "border-violet-400/40 bg-violet-500/10 text-violet-300"
                  : "border-violet-600 bg-violet-50 text-violet-700 ring-1 ring-violet-600"
                : isDark
                  ? "border-[#2a2a2a] bg-[#242424] text-zinc-300 hover:border-violet-400/40 hover:bg-violet-500/10"
                  : "border-gray-200 bg-white text-gray-600 hover:border-violet-300"
            }
          `}
        >
          自动
        </button>
        <input
          type="range"
          min={0}
          max={MAX_COUNT}
          step={STEP}
          value={isAuto ? 0 : sliderValue}
          onChange={handleSliderChange}
          className={`flex-1 h-2 rounded-lg appearance-none cursor-pointer accent-violet-600 ${
            isDark ? "bg-[#2a2a2a] accent-violet-400" : "bg-gray-200"
          }`}
        />
        <div className="relative shrink-0">
          <input
            type="text"
            inputMode="numeric"
            value={inputValue}
            onChange={handleInputChange}
            onBlur={handleInputBlur}
            placeholder="自动"
            className={`w-20 px-2 py-1.5 text-xs text-center border rounded-md focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500 ${
              isDark
                ? "border-[#2a2a2a] bg-[#242424] text-zinc-200 placeholder:text-zinc-500"
                : "border-gray-200 bg-white text-gray-900"
            }`}
          />
        </div>
          </div>
          <div
            className={`flex justify-between text-[10px] mt-1 px-[52px] ${
              isDark ? "text-zinc-500" : "text-gray-400"
            }`}
          >
            {MARKS.map((v) => (
              <span key={v}>{v.toLocaleString()}</span>
            ))}
          </div>
        </>
      ) : (
        <div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {DURATION_OPTIONS.map((option) => {
              const isSelected = selectedDurationWordCount === option.wordCount;
              return (
                <button
                  key={option.label}
                  type="button"
                  onClick={() => handleDurationSelect(option.wordCount)}
                  aria-pressed={isSelected}
                  className={`px-3 py-2 text-left rounded-lg border transition-all duration-200 ${
                    isSelected
                      ? isDark
                        ? "border-violet-400/50 bg-violet-500/10 text-violet-200"
                        : "border-violet-500 bg-violet-50 text-violet-700 ring-1 ring-violet-500"
                      : isDark
                        ? "border-[#2a2a2a] bg-[#242424] text-zinc-300 hover:border-violet-400/40"
                        : "border-gray-200 bg-white text-gray-700 hover:border-violet-300"
                  }`}
                >
                  <span className="block text-xs font-medium">{option.label}</span>
                  <span className={`block text-[10px] mt-0.5 ${isDark ? "text-zinc-500" : "text-gray-400"}`}>
                    约 {option.wordCount.toLocaleString()} 字
                  </span>
                </button>
              );
            })}
          </div>
          <p className={`text-[10px] mt-2 ${isDark ? "text-zinc-500" : "text-gray-400"}`}>
            按约 200 字/分钟估算，实际视频时长会受语速、停顿和画面节奏影响。
          </p>
        </div>
      )}
    </div>
  );
};

export default CopywritingWordCountSelector;
