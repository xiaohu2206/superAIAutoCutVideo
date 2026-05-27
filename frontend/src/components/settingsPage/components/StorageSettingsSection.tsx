import { Check, Copy, FolderOpen, HardDrive, Loader } from "lucide-react";
import React, { useState } from "react";
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
    <section className="space-y-4">
      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200/80 bg-slate-50/70 p-5 backdrop-blur-sm lg:flex-row lg:items-start lg:justify-between dark:border-slate-700/80 dark:bg-gray-800/70">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white text-slate-600 ring-1 ring-slate-200 dark:bg-gray-700 dark:text-gray-300 dark:ring-gray-600">
              <HardDrive className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h4 className="text-base font-semibold tracking-[0.02em] text-slate-900 dark:text-gray-100">存储设置</h4>
              <p className="mt-1 text-sm text-slate-500 dark:text-gray-400">管理 uploads 根路径以及历史数据迁移策略。</p>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200/80 bg-white/85 p-5 shadow-sm backdrop-blur-sm dark:border-slate-700/80 dark:bg-gray-900/85">
        <div className="space-y-5">
          <div className="space-y-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-sm font-medium text-slate-700 dark:text-gray-200">当前 uploads 根路径（缓存数据存储目录，不要出现中文路径）</p>
                <p className="mt-1 text-xs font-medium text-amber-600">更改后重启应用可生效</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={handleCopy}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100 dark:border-slate-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
                  <span>{copied ? "已复制" : "复制"}</span>
                </button>
                <button
                  onClick={pickDirectory}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
                >
                  <FolderOpen className="h-4 w-4" />
                  <span>选择目录</span>
                </button>
              </div>
            </div>
            <input
              type="text"
              value={selectedDir}
              onChange={(e) => setSelectedDir(e.target.value)}
              onBlur={() => {
                const same = (current?.uploads_root || "") === (selectedDir || "")
                if (!same && canApply) {
                  applySettings(selectedDir, migrate)
                }
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  if (canApply) {
                    applySettings(selectedDir, migrate)
                  }
                }
              }}
              placeholder="请选择或输入新的 uploads 根路径"
              className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 placeholder:text-slate-400 focus:border-blue-300 focus:outline-none focus:ring-2 focus:ring-blue-100 dark:border-slate-600 dark:bg-gray-800 dark:text-gray-200 dark:placeholder:text-gray-500 dark:focus:border-blue-600 dark:focus:ring-blue-900/30"
            />
            <div className="px-3 text-xs text-slate-500  text-gray-500">
              当前: <span className="break-all font-medium text-slate-700 dark:text-gray-200">{current?.uploads_root || "未知"}</span>
            </div>
          </div>

          <label className="flex items-start gap-3 rounded-2xl  bg-slate-50/70 px-4 py-3 cursor-pointer dark:border-slate-700 dark:bg-gray-800/70">
            <input
              type="checkbox"
              checked={migrate}
              onChange={(e) => setMigrate(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-200 dark:border-gray-600 dark:focus:ring-blue-800"
            />
              迁移旧数据
              <span className="ml-1 text-xs text-slate-500 dark:text-gray-400">(谨慎操作，迁移可能耗时)</span>
          </label>

          {error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
              {error}
            </div>
          ) : null}

          <div className="inline-flex">
            <button
              onClick={() => applySettings(selectedDir, migrate)}
              disabled={!canApply}
              className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium text-white transition-colors ${canApply ? "bg-blue-600 hover:bg-blue-700" : "bg-slate-400 cursor-not-allowed dark:bg-gray-600"}`}
            >
              {loading ? <Loader className="h-4 w-4 animate-spin" /> : null}
              <span>保存设置</span>
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}

export default StorageSettingsSection;
