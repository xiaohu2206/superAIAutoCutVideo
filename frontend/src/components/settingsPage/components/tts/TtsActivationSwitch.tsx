import React from "react";
import { CheckCircle, Power } from "lucide-react";

interface Props {
  enabled: boolean;
  onActivate: () => Promise<void> | void;
}

export const TtsActivationSwitch: React.FC<Props> = ({ enabled, onActivate }) => {
  return (
    <div className="flex items-center justify-between">
      <div className="text-sm text-gray-800">激活配置</div>
      <button
        className={`inline-flex items-center px-3 py-2 rounded-md text-sm ${enabled ? "bg-green-600 text-white" : "bg-gray-100 text-gray-800 hover:bg-gray-200"}`}
        onClick={() => onActivate()}
        disabled={enabled}
        title="设为激活配置"
      >
        {enabled ? <CheckCircle className="h-4 w-4 mr-1" /> : <Power className="h-4 w-4 mr-1" />}
        {enabled ? "已激活" : "设为激活配置"}
      </button>
    </div>
  );
};

export default TtsActivationSwitch;
