import React, { useState } from "react";
import { FolderOpen, Copy, Check, HardDrive, Loader } from "lucide-react";
import { useStorageSettings } from "../hooks/useStorageSettings";

const StorageSettingsSection: React.FC = () => {
  const {
    current,
    selectedDir,
    setSelectedDir,
    migrate,
    setMigrate,
    loading,
    error,
    pickDirectory,
    applySettings,
  } = useStorageSettings();
  const [copied, setCopied] = useState(false);

  const canApply = Boolean((selectedDir || current?.uploads_root || "").trim()) && !loading;

  const handleCopy = async () => {
    const text = current?.uploads_root || "";
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch (e) {
      setCopied(false);
    }
  };

  return (
    <section className="bg-white/80 backdrop-blur border rounded-xl p-5 shadow-sm space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <HardDrive className="h-5 w-5 text-gray-700" />
          <h4 className="text-md font-semibold text-gray-900">存储设置</h4>
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between mb-2">
            <div>
              <p className="text-sm font-medium text-gray-700">当前 uploads 根路径（缓存数据存储目录）</p>
              <p className="text-xs text-gray-500">前端始终通过 /uploads/... 访问</p>
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={handleCopy}
                className="px-2 py-1 text-xs rounded-md border hover:bg-gray-50"
              >
                <div className="flex items-center space-x-1">
                  {copied ? <Check className="h-3 w-3 text-green-600" /> : <Copy className="h-3 w-3" />}
                  <span>{copied ? "已复制" : "复制"}</span>
                </div>
              </button>
              <button
                onClick={pickDirectory}
                className="px-3 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700"
              >
                <div className="flex items-center space-x-2">
                  <FolderOpen className="h-4 w-4" />
                  <span>选择目录</span>
                </div>
              </button>
            </div>
          </div>
          <input
            type="text"
            value={selectedDir}
            onChange={(e) => setSelectedDir(e.target.value)}
            onBlur={() => {
              const same = (current?.uploads_root || "") === (selectedDir || "");
              if (!same && canApply) {
                applySettings(selectedDir, migrate);
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                if (canApply) {
                  applySettings(selectedDir, migrate);
                }
              }
            }}
            placeholder="请选择或输入新的 uploads 根路径"
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-200"
          />
          <p className="text-xs text-gray-500 mt-1">
            当前: {current?.uploads_root || "未知"}
          </p>
        </div>

        <div className="flex items-center justify-between">
          <label className="flex items-center space-x-2">
            <input
              type="checkbox"
              checked={migrate}
              onChange={(e) => setMigrate(e.target.checked)}
            />
            <span className="text-sm text-gray-700">迁移旧数据</span>
          </label>
          <span className="text-xs text-gray-500">谨慎操作，迁移可能耗时</span>
        </div>

        {error ? (
          <div className="text-sm text-red-600">{error}</div>
        ) : null}

        <div className="inline-flex">
          <button
            onClick={() => applySettings(selectedDir, migrate)}
            disabled={!canApply}
            className={`px-4 py-2 rounded-md text-white ${canApply ? "bg-blue-600 hover:bg-blue-700" : "bg-gray-400 cursor-not-allowed"}`}
          >
            <div className="flex items-center space-x-2">
              {loading ? <Loader className="h-4 w-4 animate-spin" /> : null}
              <span>保存</span>
            </div>
          </button>
        </div>
      </div>
    </section>
  );
}

export default StorageSettingsSection;
