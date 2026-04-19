import { Loader } from "lucide-react";
import React from "react";

export interface OmniFullNarrationPipelineControlsProps {
  busy: boolean;
  disabled: boolean;
  disabledReason?: string;
  onRun: () => void;
}

/**
 * Omni 专用：仅「全链路」触发按钮（进度条由 ProjectOperations 内全宽 slot 渲染，与 visual 脚本进度布局一致）。
 */
const OmniFullNarrationPipelineControls: React.FC<OmniFullNarrationPipelineControlsProps> = ({
  busy,
  disabled,
  disabledReason,
  onRun,
}) => {
  const btnDisabled = disabled || busy;

  return (
    <button
      type="button"
      onClick={onRun}
      disabled={btnDisabled}
      title={disabledReason}
      className="flex items-center justify-center px-6 py-2 bg-violet-600 text-white rounded-lg font-medium hover:bg-violet-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {busy ? (
        <>
          <Loader className="h-5 w-5 mr-2 animate-spin" />
          全链路生成中…
        </>
      ) : (
        <>生成解说脚本（Omni 全链路）</>
      )}
    </button>
  );
};

export default OmniFullNarrationPipelineControls;
