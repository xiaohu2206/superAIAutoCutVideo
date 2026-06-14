import React from "react";
import { Loader2 } from "lucide-react";
import { useOmniStep2PipelineConfig } from "../../../hooks/useOmniStep2PipelineConfig";
import type { OmniStep2LocalSettings } from "../../../types";

interface LocalFieldDefinition {
  key: keyof OmniStep2LocalSettings;
  label: string;
  hint: string;
  min: number;
  max: number;
}

const VISION_FIELDS: LocalFieldDefinition[] = [
  {
    key: "vl_batch_size",
    label: "单次调用语义段数",
    hint: "每段固定 2 帧；设为 1 表示一次只分析 1 个镜头描述段",
    min: 1,
    max: 32,
  },
  {
    key: "infer_wall_sec",
    label: "单次调用超时（秒）",
    hint: "本地视觉模型推理较慢，建议 600～1200",
    min: 30,
    max: 7200,
  },
  {
    key: "vision_api_concurrency",
    label: "视觉模型 API 并发",
    hint: "只限制视觉理解请求；本地部署建议设为 1，避免显存不足",
    min: 1,
    max: 64,
  },
];

const TEXT_FIELDS: LocalFieldDefinition[] = [
  {
    key: "text_api_concurrency",
    label: "文案模型 API 并发",
    hint: "限制文案生成、脚本生成、结构化和镜头匹配等文本 LLM 请求",
    min: 1,
    max: 64,
  },
];

interface OmniStep2LocalPipelineSettingsProps {
  modelType: "vision" | "text";
}

export const OmniStep2LocalPipelineSettings: React.FC<
  OmniStep2LocalPipelineSettingsProps
> = ({ modelType }) => {
  const {
    root,
    loading,
    saving,
    toggling,
    togglingVision,
    togglingText,
    setUseLocalModel,
    setLocalField,
  } = useOmniStep2PipelineConfig();

  const renderFields = (fields: LocalFieldDefinition[], toggling: boolean) => (
    <div className="mt-4 space-y-3 border-t border-slate-200 pt-4 dark:border-slate-700">
      {fields.map(({ key, label, hint, min, max }) => (
        <div key={key}>
          <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
            {label}
          </label>
          <input
            type="number"
            min={min}
            max={max}
            className="w-full max-w-xs rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-slate-600 dark:bg-[#1a1a1a]"
            value={root.local[key]}
            disabled={loading || toggling}
            onChange={(e) => {
              const n = parseInt(e.target.value, 10);
              if (!Number.isFinite(n)) return;
              setLocalField(key, Math.min(max, Math.max(min, n)));
            }}
          />
          <p className="mt-1 text-xs text-slate-500 dark:text-gray-400">{hint}</p>
        </div>
      ))}
    </div>
  );

  const renderStatus = (toggling: boolean) => {
    if (toggling) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          切换中…
        </span>
      );
    }
    if (saving) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          保存中…
        </span>
      );
    }
    return null;
  };

  if (modelType === "vision") {
    return (
      <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-700 dark:bg-gray-900/40">
        <div className={`flex items-start gap-3 ${togglingVision ? "opacity-90" : ""}`}>
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:cursor-wait"
            checked={root.use_local_vision_model}
            disabled={loading || toggling}
            onChange={(e) => void setUseLocalModel("vision", e.target.checked)}
            aria-describedby="local-vision-model-hint"
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-900 dark:text-gray-100">
                视觉模型-使用本地模型
              </span>
              {renderStatus(togglingVision)}
            </div>
            <p id="local-vision-model-hint" className="mt-1 text-xs text-slate-500 dark:text-gray-400">
              只影响视频画面理解。开启后使用小批量、低并发和长超时，不会改变文案模型并发。
            </p>
          </div>
        </div>
        {root.use_local_vision_model && renderFields(VISION_FIELDS, toggling)}
        {root.use_local_vision_model && root.effective && (
          <p className="mt-3 text-xs text-slate-500 dark:text-gray-400">
            当前视觉参数：每批 {root.effective.vl_batch_images} 张图，API 并发 {root.effective.vision_api_concurrency}，超时 {root.effective.infer_wall_sec} 秒
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-700 dark:bg-gray-900/40">
      <div className={`flex items-start gap-3 ${togglingText ? "opacity-90" : ""}`}>
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:cursor-wait"
          checked={root.use_local_text_model}
          disabled={loading || toggling}
          onChange={(e) => void setUseLocalModel("text", e.target.checked)}
          aria-describedby="local-text-model-hint"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-slate-900 dark:text-gray-100">
              文案模型-使用本地模型
            </span>
            {renderStatus(togglingText)}
          </div>
          <p id="local-text-model-hint" className="mt-1 text-xs text-slate-500 dark:text-gray-400">
            只影响文案、脚本及其他文本 LLM 调用。开启后降低文本并发，不会改变视觉分析参数。
          </p>
        </div>
      </div>
      {root.use_local_text_model && renderFields(TEXT_FIELDS, toggling)}
      {root.use_local_text_model && root.effective && (
        <p className="mt-3 text-xs text-slate-500 dark:text-gray-400">
          当前文案模型 API 并发：{root.effective.text_api_concurrency}
        </p>
      )}
    </div>
  );
};
