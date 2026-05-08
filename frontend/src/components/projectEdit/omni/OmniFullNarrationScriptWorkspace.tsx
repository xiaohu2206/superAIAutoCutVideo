import { Loader, Save } from "lucide-react";
import React from "react";

export interface OmniFullNarrationScriptWorkspaceProps {
  editedScript: string;
  setEditedScript: (script: string) => void;
  isSaving: boolean;
  onSave: () => void;
}

/**
 * Omni 专用脚本 JSON 编辑区：布局参考 ScriptJsonEditor 的 editedScript 用法，但不 import 该组件。
 */
const OmniFullNarrationScriptWorkspace: React.FC<OmniFullNarrationScriptWorkspaceProps> = ({
  editedScript,
  setEditedScript,
  isSaving,
  onSave,
}) => {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">Omni 解说脚本（JSON）</h2>
        <button
          type="button"
          onClick={onSave}
          disabled={!editedScript.trim() || isSaving}
          className="flex items-center px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? (
            <>
              <Loader className="h-4 w-4 mr-2 animate-spin" />
              保存中...
            </>
          ) : (
            <>
              <Save className="h-4 w-4" />
            </>
          )}
        </button>
      </div>

      <p className="text-sm text-gray-600">
        使用「生成解说脚本（Omni 全链路）」完成后，脚本 JSON 会出现在下方；可编辑后保存。
      </p>

      <div className="relative">
        <textarea
          value={editedScript}
          onChange={(e) => setEditedScript(e.target.value)}
          placeholder="脚本数据将以 JSON 格式显示在这里..."
          className="w-full h-[600px] px-4 py-3 font-mono text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-violet-500 focus:border-transparent outline-none transition-all resize-none"
        />
        {editedScript ? (
          <div className="absolute top-2 right-2 bg-gray-100 px-2 py-1 rounded text-xs text-gray-600">JSON 格式</div>
        ) : null}
      </div>

      {!editedScript ? (
        <div className="bg-violet-50 border border-violet-200 rounded-lg p-4">
          <p className="text-sm text-violet-900 font-medium mb-2">脚本 JSON 结构示例：</p>
          <pre className="text-xs text-violet-800 overflow-x-auto">
            {`{
  "version": "1.0",
  "total_duration": 120.5,
  "segments": [
    {
      "id": "1",
      "start_time": 0.0,
      "end_time": 5.5,
      "text": "解说文本",
      "subtitle": "字幕"
    }
  ],
  "metadata": {}
}`}
          </pre>
        </div>
      ) : null}
    </div>
  );
};

export default OmniFullNarrationScriptWorkspace;
