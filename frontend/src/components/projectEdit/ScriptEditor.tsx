import React from "react";
import {
  Loader,
  Save,
} from "lucide-react";

interface ScriptEditorProps {
  editedScript: string;
  setEditedScript: (script: string) => void;
  isSaving: boolean;
  handleSaveScript: () => void;
}

const ScriptEditor: React.FC<ScriptEditorProps> = ({
  editedScript,
  setEditedScript,
  isSaving,
  handleSaveScript,
}) => {
  return (
    <div className="bg-white rounded-lg shadow-md p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">视频脚本</h2>
        <button
          onClick={handleSaveScript}
          disabled={!editedScript.trim() || isSaving}
          className="flex items-center px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? (
            <>
              <Loader className="h-4 w-4 mr-2 animate-spin" />
              保存中...
            </>
          ) : (
            <>
              <Save className="h-4 w-4 mr-2" />
              保存脚本
            </>
          )}
        </button>
      </div>

      <p className="text-sm text-gray-600">
        点击"生成解说脚本"后，脚本数据将显示在下方的编辑器中，您可以修改后保存。
      </p>

      {/* JSON 编辑器 */}
      <div className="relative">
        <textarea
          value={editedScript}
          onChange={(e) => setEditedScript(e.target.value)}
          placeholder="脚本数据将以 JSON 格式显示在这里..."
          className="w-full h-96 px-4 py-3 font-mono text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none"
        />
        {editedScript && (
          <div className="absolute top-2 right-2 bg-gray-100 px-2 py-1 rounded text-xs text-gray-600">
            JSON 格式
          </div>
        )}
      </div>

      {/* 脚本示例提示 */}
      {!editedScript && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <p className="text-sm text-blue-800 font-medium mb-2">
            脚本 JSON 格式示例：
          </p>
          <pre className="text-xs text-blue-700 overflow-x-auto">
            {`{
  "version": "1.0",
  "total_duration": 120.5,
  "segments": [
    {
      "id": "1",
      "start_time": 0.0,
      "end_time": 5.5,
      "text": "这是解说文本",
      "subtitle": "对应的字幕"
    }
  ],
  "metadata": {
    "video_name": "视频名称",
    "created_at": "2024-01-01T00:00:00Z"
  }
}`}
          </pre>
        </div>
      )}
    </div>
  );
};

export default ScriptEditor;
