import { Loader } from "lucide-react";
import React from "react";
import type { OmniStepTestPhase } from "../../../hooks/omni/useOmniFullNarrationPipeline";

export interface OmniFullNarrationPipelineControlsProps {
  /** 全链路或任一单步运行中 */
  busy: boolean;
  disabled: boolean;
  disabledReason?: string;
  omniPipelineBusy: boolean;
  omniStepTestPhase: OmniStepTestPhase | null;
  /** 勾选后跳过解说脚本大模型生成，直接用上一步候选拼装以省成本 */
  skipGenerateScriptLlm: boolean;
  onToggleSkipGenerateScriptLlm: (value: boolean) => void;
  /** 「使用本地模型」是否开启（用于复选框提示） */
  localModelPipelineEnabled: boolean;
  onRun: () => void;
  onRunStepEmbed: () => void;
  onRunStepShotMatch: () => void;
  onRunStepGenerateScript: () => void;
}

/**
 * Omni：全链路触发 + 三个单步测试按钮（与 visual 脚本进度布局一致的上层 slot）。
 */
const OmniFullNarrationPipelineControls: React.FC<OmniFullNarrationPipelineControlsProps> = ({
  busy,
  disabled,
  disabledReason,
  omniPipelineBusy,
  omniStepTestPhase,
  skipGenerateScriptLlm,
  onToggleSkipGenerateScriptLlm,
  localModelPipelineEnabled,
  onRun,
  onRunStepEmbed,
  onRunStepShotMatch,
  onRunStepGenerateScript,
}) => {
  const btnDisabled = disabled || busy;

  const stepSpin = (phase: OmniStepTestPhase) =>
    busy && omniStepTestPhase === phase && !omniPipelineBusy ? (
      <Loader className="h-4 w-4 mr-1.5 animate-spin shrink-0" />
    ) : null;

  return (
    <div className="flex flex-col gap-3 items-stretch max-w-xl">
      {/* <div className="rounded-lg border border-dashed border-amber-300/80 bg-amber-50/60 px-3 py-2">
        <div className="text-xs text-amber-900/80 mb-2 font-medium">分步测试（按全链路顺序点击）</div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onRunStepEmbed}
            disabled={btnDisabled}
            title={disabledReason}
            className="inline-flex items-center justify-center px-3 py-1.5 text-sm bg-white text-amber-900 border border-amber-400 rounded-md hover:bg-amber-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {stepSpin("embed")}
            ① 文案结构化 + 向量
          </button>
          <button
            type="button"
            onClick={onRunStepShotMatch}
            disabled={btnDisabled}
            title={disabledReason}
            className="inline-flex items-center justify-center px-3 py-1.5 text-sm bg-white text-amber-900 border border-amber-400 rounded-md hover:bg-amber-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {stepSpin("shotMatch")}
            ② 镜头匹配
          </button>
          <button
            type="button"
            onClick={onRunStepGenerateScript}
            disabled={btnDisabled}
            title={disabledReason}
            className="inline-flex items-center justify-center px-3 py-1.5 text-sm bg-white text-amber-900 border border-amber-400 rounded-md hover:bg-amber-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {stepSpin("generateScript")}
            ③ 解说脚本生成
          </button>
        </div>
      </div> */}

      <label
        className="flex items-start gap-2 cursor-pointer select-none text-sm text-gray-600"
        title="勾选后不调用大模型，直接用上一步镜头匹配候选每条 Top1 的时间拼装解说脚本，可显著节省成本"
      >
        <input
          type="checkbox"
          checked={skipGenerateScriptLlm}
          disabled={busy}
          onChange={(e) => onToggleSkipGenerateScriptLlm(e.target.checked)}
          className="mt-0.5 h-4 w-4 shrink-0 accent-violet-600 disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <span>
          跳过大模型（省成本）
          {localModelPipelineEnabled ? (
            <span className="ml-1 text-violet-600">· 已开启本地模型，默认勾选</span>
          ) : null}
        </span>
      </label>

      <button
        type="button"
        onClick={onRun}
        disabled={btnDisabled}
        title={disabledReason}
        className="flex items-center justify-center px-6 py-2 bg-violet-600 text-white rounded-lg font-medium hover:bg-violet-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {omniPipelineBusy ? (
          <>
            <Loader className="h-5 w-5 mr-2 animate-spin" />
            生成中…
          </>
        ) : (
          <>生成解说脚本</>
        )}
      </button>
    </div>
  );
};

export default OmniFullNarrationPipelineControls;
