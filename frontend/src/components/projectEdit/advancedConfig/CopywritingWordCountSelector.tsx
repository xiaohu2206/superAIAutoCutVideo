import React, { useCallback, useEffect, useRef, useState } from "react";

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

const CopywritingWordCountSelector: React.FC<Props> = ({
  copywritingWordCount,
  loading,
  saving,
  setCopywritingWordCountAndPersist,
}) => {
  const isAuto = copywritingWordCount === null || copywritingWordCount === undefined;
  const sliderValue = isAuto ? 0 : Math.max(MIN_COUNT, Math.min(MAX_COUNT, copywritingWordCount));

  const [inputValue, setInputValue] = useState<string>(isAuto ? "" : String(sliderValue));
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setInputValue(isAuto ? "" : String(sliderValue));
  }, [isAuto, sliderValue]);

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
    setInputValue("");
    void setCopywritingWordCountAndPersist(null);
  };

  return (
    <div className="border-t border-gray-200 pt-4">
      <div className="flex items-center justify-between mb-2">
        <label className="block text-sm font-medium text-gray-700">解说文案字数</label>
        {loading ? (
          <span className="text-xs text-gray-500">加载中</span>
        ) : saving ? (
          <span className="text-xs text-gray-500">保存中</span>
        ) : (
          <span className="text-xs text-gray-500">
            {isAuto ? "自动（由模型决定）" : `${sliderValue.toLocaleString()} 字`}
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleAutoClick}
          className={`
            shrink-0 px-3 py-1.5 text-xs rounded-md border transition-all duration-200
            ${
              isAuto
                ? "border-violet-600 bg-violet-50 text-violet-700 ring-1 ring-violet-600"
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
          className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-violet-600"
        />
        <div className="relative shrink-0">
          <input
            type="text"
            inputMode="numeric"
            value={inputValue}
            onChange={handleInputChange}
            onBlur={handleInputBlur}
            placeholder="自动"
            className="w-20 px-2 py-1.5 text-xs text-center border border-gray-200 rounded-md focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500"
          />
        </div>
      </div>
      <div className="flex justify-between text-[10px] text-gray-400 mt-1 px-[52px]">
        {MARKS.map((v) => (
          <span key={v}>{v.toLocaleString()}</span>
        ))}
      </div>
    </div>
  );
};

export default CopywritingWordCountSelector;
