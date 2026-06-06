import React from "react";
import { Loader2 } from "lucide-react";
import { useOmniStep2PipelineConfig } from "../../../hooks/useOmniStep2PipelineConfig";
import type { OmniStep2LocalSettings } from "../../../types";

const LOCAL_FIELDS: Array<{
  key: keyof OmniStep2LocalSettings;
  label: string;
  hint: string;
  min: number;
  max: number;
}> = [
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
    hint: "本地模型推理较慢，建议 600～1200",
    min: 30,
    max: 7200,
  },
  {
    key: "api_concurrency",
    label: "视觉模型 API 并发",
    hint: "本地部署建议 1，避免 OOM",
    min: 1,
    max: 64,
  },
];

export const OmniStep2LocalPipelineSettings: React.FC = () => {
  const { root, loading, saving, toggling, setUseLocalModelPipeline, setLocalField } =
    useOmniStep2PipelineConfig();

  const enabled = root.use_local_model_pipeline;

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-700 dark:bg-gray-900/40">
      <div
        className={`flex items-start gap-3 ${toggling ? "opacity-90" : ""}`}
        aria-busy={toggling}
      >
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:cursor-wait"
          checked={enabled}
          disabled={toggling || loading}
          onChange={(e) => void setUseLocalModelPipeline(e.target.checked)}
          aria-describedby="omni-local-pipeline-hint"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-slate-900 dark:text-gray-100">
              使用本地模型（低并发）
            </span>
            {toggling && (
              <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                切换中…
              </span>
            )}
            {saving && !toggling && (
              <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-gray-400">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                保存中…
              </span>
            )}
          </div>
          <p
            id="omni-local-pipeline-hint"
            className="mt-1 text-xs text-slate-500 dark:text-gray-400"
          >
            默认关闭，使用云端/API 默认参数（批大小 6 段、API 并发 64、超时 40 秒）。
            开启后降低 API 并发与超时,并发默认1，超时默认1200秒，本地会很慢。
          </p>
        </div>
      </div>

      {enabled && (
        <div className="mt-4 space-y-3 border-t border-slate-200 pt-4 dark:border-slate-700">
          {LOCAL_FIELDS.map(({ key, label, hint, min, max }) => (
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
          {root.effective && (
            <p className="text-xs text-slate-500 dark:text-gray-400">
              当前生效：每批 {root.effective.vl_batch_images} 张图（
              {root.effective.vl_batch_size} 段 × {root.effective.frames_per_shot} 帧），API 并发{" "}
              {root.effective.api_concurrency}，超时 {root.effective.infer_wall_sec} 秒
            </p>
          )}
        </div>
      )}
    </div>
  );
};
