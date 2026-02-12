import { AlertCircle, Cpu, Loader, RefreshCw } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { concurrencyService, GenerateConcurrencyData } from "../../../services/concurrencyService";
import { useDebouncedCallback } from "../../../hooks/useDebouncedCallback";

const ConcurrencyItem: React.FC<{
  title: string;
  scopeKey: "generate_video" | "generate_jianying_draft";
  data: GenerateConcurrencyData | null;
  onChange: (scope: string, val: number, override: boolean) => void;
  description: string;
}> = ({ title, scopeKey, data, onChange, description }) => {
  if (!data) return null;
  
  const config = data.config[scopeKey];
  const effective = data.effective[scopeKey];
  
  // 是否启用了自定义
  const isOverridden = config.override === true;
  // 当前配置值
  const configValue = config.max_workers;
  // 实际生效值
  const effectiveValue = effective.max_workers;
  // 生效来源
  const sourceMap: Record<string, string> = {
    user: "用户设置",
    env: "环境变量",
    recommended: "系统推荐",
  };
  const sourceLabel = sourceMap[effective.source] || effective.source;

  return (
    <div className="p-4 border rounded-lg bg-gray-50/50 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="font-medium text-gray-900">{title}</h4>
          <p className="text-xs text-gray-500 mt-0.5">{description}</p>
        </div>
        <div className="text-right">
          <div className="text-sm font-semibold text-blue-600">
            当前生效: {effectiveValue} 并发
          </div>
          <div className="text-xs text-gray-500">
            来源: {sourceLabel}
          </div>
        </div>
      </div>

      <div className="flex items-center space-x-4 pt-2">
        <label className="flex items-center space-x-2 text-sm text-gray-700 cursor-pointer">
          <input
            type="checkbox"
            checked={isOverridden}
            onChange={(e) => onChange(scopeKey, configValue, e.target.checked)}
            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <span>启用自定义设置</span>
        </label>

        <div className="flex-1 flex items-center space-x-3">
          <input
            type="range"
            min="1"
            max="16"
            step="1"
            disabled={!isOverridden}
            value={configValue}
            onChange={(e) => onChange(scopeKey, parseInt(e.target.value) || 1, true)}
            className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer disabled:opacity-50"
          />
          <input
            type="number"
            min="1"
            max="32"
            disabled={!isOverridden}
            value={configValue}
            onChange={(e) => onChange(scopeKey, parseInt(e.target.value) || 1, true)}
            className="w-16 px-2 py-1 text-sm border border-gray-300 rounded-md focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-100 disabled:text-gray-400"
          />
        </div>
      </div>
    </div>
  );
};

export const GlobalParamsSettings: React.FC = () => {
  const [data, setData] = useState<GenerateConcurrencyData | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedHint, setSavedHint] = useState<string | null>(null);
  const [savedHintVisible, setSavedHintVisible] = useState(false);

  const dataRef = useRef<GenerateConcurrencyData | null>(null);
  const savingRef = useRef(false);
  const resizingRef = useRef(false);
  const loadingRef = useRef(false);
  const dirtyRef = useRef(false);
  const queuedSaveRef = useRef(false);
  const savedHintTimerRef = useRef<number | null>(null);

  useEffect(() => {
    dataRef.current = data;
  }, [data]);

  useEffect(() => {
    savingRef.current = saving;
  }, [saving]);

  useEffect(() => {
    resizingRef.current = resizing;
  }, [resizing]);

  useEffect(() => {
    loadingRef.current = loading;
  }, [loading]);

  useEffect(() => {
    return () => {
      if (savedHintTimerRef.current !== null) {
        window.clearTimeout(savedHintTimerRef.current);
      }
    };
  }, []);

  const flashSavedHint = useCallback((hint: string) => {
    setSavedHint(hint);
    setSavedHintVisible(true);
    if (savedHintTimerRef.current !== null) {
      window.clearTimeout(savedHintTimerRef.current);
    }
    savedHintTimerRef.current = window.setTimeout(() => {
      setSavedHintVisible(false);
    }, 1800);
  }, []);

  const performAutoSave = useCallback(async () => {
    const snapshot = dataRef.current;
    if (!snapshot) return;
    if (!dirtyRef.current) return;

    if (savingRef.current || resizingRef.current || loadingRef.current) {
      queuedSaveRef.current = true;
      return;
    }

    dirtyRef.current = false;
    setSaving(true);
    setError(null);

    try {
      const resp = await concurrencyService.updateConcurrency({
        generate_video: snapshot.config.generate_video,
        generate_jianying_draft: snapshot.config.generate_jianying_draft,
        allow_same_project_parallel: snapshot.config.allow_same_project_parallel,
      });

      if (resp?.data) {
        setData(resp.data);
      }

      setResizing(true);
      try {
        await concurrencyService.resizeConcurrency();
        flashSavedHint("已保存并生效");
      } catch (resizeErr) {
        console.warn("Resize failed:", resizeErr);
        flashSavedHint("已保存 (运行时调整失败)");
      } finally {
        setResizing(false);
      }
    } catch (e: any) {
      dirtyRef.current = true;
      setError(e.message || "保存失败");
    } finally {
      setSaving(false);
      if (queuedSaveRef.current) {
        queuedSaveRef.current = false;
        void performAutoSave();
      }
    }
  }, [flashSavedHint]);

  const [scheduleAutoSave, cancelAutoSave] = useDebouncedCallback(() => performAutoSave(), 600);

  const resetAutoSaveState = useCallback(() => {
    cancelAutoSave();
    queuedSaveRef.current = false;
    dirtyRef.current = false;
  }, [cancelAutoSave]);

  const loadData = useCallback(async () => {
    resetAutoSaveState();
    setLoading(true);
    setError(null);
    try {
      const resp = await concurrencyService.getConcurrency();
      if (resp?.data) {
        setData(resp.data);
      }
    } catch (e: any) {
      setError(e.message || "加载配置失败");
    } finally {
      setLoading(false);
    }
  }, [resetAutoSaveState]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // 本地修改 state
  const handleScopeChange = useCallback(
    (scope: string, val: number, override: boolean) => {
      dirtyRef.current = true;
      const key = scope as "generate_video" | "generate_jianying_draft";
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          config: {
            ...prev.config,
            [key]: {
              max_workers: val,
              override: override,
            },
          },
        };
      });
      scheduleAutoSave();
    },
    [scheduleAutoSave]
  );

  const handleAllowParallelChange = useCallback(
    (checked: boolean) => {
      dirtyRef.current = true;
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          config: {
            ...prev.config,
            allow_same_project_parallel: checked,
          },
        };
      });
      scheduleAutoSave();
    },
    [scheduleAutoSave]
  );

  if (loading && !data) {
    return (
      <div className="flex justify-center items-center py-12 text-gray-500">
        <Loader className="h-6 w-6 animate-spin mr-2" />
        加载中...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Cpu className="h-5 w-5 text-gray-700" />
          <h4 className="text-md font-semibold text-gray-900">生成并发控制</h4>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-xs text-gray-500 flex items-center">
            {(saving || resizing) && <Loader className="h-3.5 w-3.5 mr-1.5 animate-spin" />}
            {saving ? "保存中..." : resizing ? "应用中..." : savedHintVisible ? (savedHint || "已保存") : "自动保存"}
          </div>
          <button
            onClick={loadData}
            disabled={loading || saving || resizing}
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-transparent"
            title="刷新配置"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="bg-blue-50 border border-blue-100 rounded-md p-3 flex items-start space-x-2">
        <AlertCircle className="h-5 w-5 text-blue-600 mt-0.5 flex-shrink-0" />
        <div className="text-sm text-blue-800">
          <p className="font-medium">关于并发设置</p>
          <p className="mt-1 opacity-90">
            增加并发数可以提高任务处理速度，但会占用更多的 CPU、内存和显存资源。
            如果设置过高，可能导致系统卡顿或任务失败（OOM）。
            建议保持“系统推荐”设置，除非您确信机器有足够的资源。
          </p>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-100 rounded-md p-3 text-sm text-red-600 flex items-center">
          <AlertCircle className="h-4 w-4 mr-2" />
          {error}
        </div>
      )}

      <div className="space-y-4">
        <ConcurrencyItem
          title="视频生成并发数"
          scopeKey="generate_video"
          data={data}
          onChange={handleScopeChange}
          description="同时进行的视频生成任务数量 (消耗 CPU/GPU/内存)"
        />

        <ConcurrencyItem
          title="剪映草稿生成并发数"
          scopeKey="generate_jianying_draft"
          data={data}
          onChange={handleScopeChange}
          description="同时进行的剪映草稿生成任务数量 (主要消耗磁盘 IO)"
        />

        <div className="p-4 border rounded-lg bg-gray-50/50 flex items-center justify-between">
          <div>
            <h4 className="font-medium text-gray-900">允许同一项目并行任务</h4>
            <p className="text-xs text-gray-500 mt-0.5">
              是否允许对同一个项目 ID 同时发起多个生成任务。关闭后，重复提交会返回正在运行的任务。
            </p>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              className="sr-only peer"
              checked={data?.config.allow_same_project_parallel || false}
              onChange={(e) => handleAllowParallelChange(e.target.checked)}
            />
            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
          </label>
        </div>
      </div>
    </div>
  );
};

export default GlobalParamsSettings;
