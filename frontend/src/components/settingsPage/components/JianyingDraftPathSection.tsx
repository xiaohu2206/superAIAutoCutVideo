import { CheckCircle, FolderOpen, Loader, Search, UploadCloud, XCircle } from "lucide-react";
import React, { useEffect, useState } from "react";
import { jianyingService } from "../../../services/jianyingService";
import { TauriCommands } from "../../../services/tauriService";

export const JianyingDraftPathSection: React.FC = () => {
  const [path, setPath] = useState<string>("");
  const [exists, setExists] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [detecting, setDetecting] = useState<boolean>(false);

  const loadCurrent = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await jianyingService.getDraftPath();
      if (resp.success) {
        setPath(resp.data?.path || "");
        setExists(Boolean(resp.data?.exists));
      }
    } catch (e: any) {
      setError(e?.message || "加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadCurrent();
  }, []);

  const handleDetect = async () => {
    setDetecting(true);
    setError(null);
    try {
      const resp = await jianyingService.detectDraftPath();
      const selected = resp?.data?.selected as string | undefined;
      if (selected) {
        setPath(selected);
        setExists(true);
      } else {
        setError("未找到剪映草稿路径，请手动选择");
      }
    } catch (e: any) {
      setError(e?.message || "自动查找失败");
    } finally {
      setDetecting(false);
    }
  };

  const handleBrowse = async () => {
    try {
      const res = await TauriCommands.selectOutputDirectory();
      if (!res.cancelled && res.path) {
        setPath(res.path);
        setExists(true);
      }
    } catch (e: any) {
      setError(e?.message || "浏览选择失败");
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const resp = await jianyingService.setDraftPath(path);
      if (resp.success) {
        setExists(Boolean(resp.data?.exists));
      } else {
        setError(resp.message || "保存失败");
      }
    } catch (e: any) {
      setError(e?.message || "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="text-sm text-gray-700">
        配置剪映草稿存放路径，便于生成的草稿zip自动复制到剪映项目目录中。
      </div>

      {error ? (
        <div className="flex items-center text-sm text-red-600">
          <XCircle className="h-4 w-4 mr-1" />
          {error}
        </div>
      ) : null}

      <div className="space-y-2">
        <label className="block text-sm text-gray-700">草稿路径</label>
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="请选择或输入剪映草稿目录"
            className="px-3 py-2 border border-gray-300 rounded-md w-full"
          />
          <button
            className="inline-flex items-center px-3 py-2 rounded-md text-sm bg-gray-100 text-gray-800 hover:bg-gray-200"
            onClick={handleBrowse}
            title="浏览选择目录"
          >
            <FolderOpen className="h-4 w-4 mr-1" />
            浏览
          </button>
        </div>
        <div className="flex items-center text-sm">
          {exists ? (
            <span className="inline-flex items-center text-green-600">
              <CheckCircle className="h-4 w-4 mr-1" />
              路径有效
            </span>
          ) : (
            <span className="inline-flex items-center text-gray-500">
              路径未知或不存在
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          className={`inline-flex items-center px-3 py-2 rounded-md text-sm ${
            detecting ? "bg-gray-200 text-gray-500 cursor-not-allowed" : "bg-gray-100 hover:bg-gray-200 text-gray-800"
          }`}
          onClick={handleDetect}
          disabled={detecting}
          title="自动查找剪映草稿路径"
        >
          {detecting ? <Loader className="h-4 w-4 mr-1 animate-spin" /> : <Search className="h-4 w-4 mr-1" />}
          自动查找
        </button>
        <button
          className={`inline-flex items-center px-3 py-2 rounded-md text-sm ${
            saving ? "bg-blue-200 text-white cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700 text-white"
          }`}
          onClick={handleSave}
          disabled={saving || !path}
          title="保存配置"
        >
          {saving ? <Loader className="h-4 w-4 mr-1 animate-spin" /> : <UploadCloud className="h-4 w-4 mr-1" />}
          保存
        </button>
        {loading ? <span className="inline-flex items-center text-xs text-gray-500">加载中...</span> : null}
      </div>
    </div>
  );
};

export default JianyingDraftPathSection;

