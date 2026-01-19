import { Check, Copy, Plus, Trash2, X } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { usePrompts } from "../../hooks/usePrompts";
import type { CreatePromptPayload } from "../../types/prompts";
import { NarrationType, type ScriptLengthOption } from "../../types/project";
import { projectService } from "../../services/projectService";

interface GenerateAdvancedConfigSectionProps {
  projectId: string;
  narrationType?: NarrationType;
}

const DEFAULT_SCRIPT_LENGTH: ScriptLengthOption = "30～40条";

const SCRIPT_LENGTH_OPTIONS: Array<{
  value: ScriptLengthOption;
  title: string;
  subtitle: string;
}> = [
  { value: "15～20条", title: "15～20 条", subtitle: "预计最少 2 次模型调用" },
  { value: "30～40条", title: "30～40 条", subtitle: "预计最少 4 次模型调用" },
  { value: "40～60条", title: "40～60 条", subtitle: "预计最少 5 次模型调用" },
  { value: "60～80条", title: "60～80 条", subtitle: "预计最少 6 次模型调用" },
  { value: "80～100条", title: "80～100 条", subtitle: "预计最少 7 次模型调用" },
];

const CUSTOM_SCRIPT_LENGTH_MIN = 5;
const CUSTOM_SCRIPT_LENGTH_MAX = 200;
const ORIGINAL_RATIO_MIN = 10;
const ORIGINAL_RATIO_MAX = 90;
const DEFAULT_ORIGINAL_RATIO = 70;

const normalizeRangeSeparators = (value: string) =>
  value
    .replace(/\s+/g, "")
    .replace("~", "～")
    .replace("-", "～")
    .replace("—", "～")
    .replace("–", "～");

const parseRangeFromString = (value: string): { min: number; max: number } | null => {
  const cleaned = normalizeRangeSeparators(value);
  const match = cleaned.match(/(\d+)\D+(\d+)/);
  if (!match) return null;
  const a = Number(match[1]);
  const b = Number(match[2]);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  const min = Math.min(a, b);
  const max = Math.max(a, b);
  if (min <= 0 || max <= 0) return null;
  return { min, max };
};

const computeCustomRange = (target: number): { min: number; max: number } | null => {
  if (!Number.isFinite(target)) return null;
  const safe = Math.max(CUSTOM_SCRIPT_LENGTH_MIN, Math.min(CUSTOM_SCRIPT_LENGTH_MAX, Math.round(target)));
  if (safe <= 0) return null;
  const min = Math.max(CUSTOM_SCRIPT_LENGTH_MIN, Math.floor(safe * 0.8));
  const max = Math.max(min, Math.ceil(safe * 1.2));
  return { min, max: Math.min(CUSTOM_SCRIPT_LENGTH_MAX, max) };
};

const formatRangeValue = (range: { min: number; max: number }): ScriptLengthOption =>
  `${range.min}～${range.max}条`;

const formatRangeTitle = (range: { min: number; max: number }) => `${range.min}～${range.max} 条`;

const estimateCallsForDisplay = (maxCount: number) => {
  if (maxCount <= 20) return 2;
  if (maxCount <= 40) return 4;
  if (maxCount <= 60) return 5;
  if (maxCount <= 80) return 6;
  if (maxCount <= 100) return 7;
  return 7 + Math.ceil((maxCount - 100) / 20);
};

const normalizeScriptLengthString = (value: string): ScriptLengthOption | null => {
  const cleaned = normalizeRangeSeparators(value);
  if (!cleaned) return null;
  const presetRange = parseRangeFromString(cleaned);
  if (presetRange) return formatRangeValue(presetRange);
  const numMatch = cleaned.match(/(\d+)/);
  if (numMatch) {
    const range = computeCustomRange(Number(numMatch[1]));
    return range ? formatRangeValue(range) : null;
  }
  return null;
};

const normalizeScriptLength = (value: unknown): ScriptLengthOption => {
  const v = typeof value === "string" ? value : "";
  const allowed = new Set<ScriptLengthOption>([
    "15～20条",
    "30～40条",
    "40～60条",
    "60～80条",
    "80～100条",
  ]);
  if (allowed.has(v as ScriptLengthOption)) return v as ScriptLengthOption;
  if (v === "短篇") return "15～20条";
  if (v === "中偏") return "40～60条";
  if (v === "长偏") return "80～100条";
  const normalized = normalizeScriptLengthString(v);
  if (normalized) return normalized;
  return DEFAULT_SCRIPT_LENGTH;
};

const normalizeOriginalRatio = (value: unknown): number => {
  const num = Number(value);
  if (!Number.isFinite(num)) return DEFAULT_ORIGINAL_RATIO;
  const rounded = Math.round(num);
  return Math.min(ORIGINAL_RATIO_MAX, Math.max(ORIGINAL_RATIO_MIN, rounded));
};

function useProjectScriptLength(projectId: string): {
  scriptLength: ScriptLengthOption;
  loading: boolean;
  saving: boolean;
  setScriptLengthAndPersist: (value: ScriptLengthOption) => Promise<void>;
} {
  const [scriptLength, setScriptLength] = useState<ScriptLengthOption>(DEFAULT_SCRIPT_LENGTH);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveSeqRef = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = await projectService.getProject(projectId);
      const normalized = normalizeScriptLength(p?.script_length);
      setScriptLength(normalized);

      if (p?.script_length && p.script_length !== normalized) {
        const seq = ++saveSeqRef.current;
        setSaving(true);
        try {
          await projectService.updateProjectQueued(projectId, { script_length: normalized });
        } catch {
          void 0;
        } finally {
          if (saveSeqRef.current === seq) setSaving(false);
        }
      }
    } catch {
      void 0;
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setScriptLengthAndPersist = useCallback(
    async (value: ScriptLengthOption) => {
      setScriptLength(value);
      const seq = ++saveSeqRef.current;
      setSaving(true);
      try {
        await projectService.updateProjectQueued(projectId, { script_length: value });
      } catch {
        void 0;
      } finally {
        if (saveSeqRef.current === seq) setSaving(false);
      }
    },
    [projectId]
  );

  return { scriptLength, loading, saving, setScriptLengthAndPersist };
}

function useProjectOriginalRatio(projectId: string): {
  originalRatio: number;
  loading: boolean;
  saving: boolean;
  setOriginalRatioAndPersist: (value: number) => Promise<void>;
} {
  const [originalRatio, setOriginalRatio] = useState(DEFAULT_ORIGINAL_RATIO);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveSeqRef = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = await projectService.getProject(projectId);
      const normalized = normalizeOriginalRatio(p?.original_ratio);
      setOriginalRatio(normalized);

      if (p?.original_ratio !== undefined && p.original_ratio !== normalized) {
        const seq = ++saveSeqRef.current;
        setSaving(true);
        try {
          await projectService.updateProjectQueued(projectId, { original_ratio: normalized });
        } catch {
          void 0;
        } finally {
          if (saveSeqRef.current === seq) setSaving(false);
        }
      }
    } catch {
      void 0;
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setOriginalRatioAndPersist = useCallback(
    async (value: number) => {
      const normalized = normalizeOriginalRatio(value);
      setOriginalRatio(normalized);
      const seq = ++saveSeqRef.current;
      setSaving(true);
      try {
        await projectService.updateProjectQueued(projectId, { original_ratio: normalized });
      } catch {
        void 0;
      } finally {
        if (saveSeqRef.current === seq) setSaving(false);
      }
    },
    [projectId]
  );

  return { originalRatio, loading, saving, setOriginalRatioAndPersist };
}

const GenerateAdvancedConfigSection: React.FC<GenerateAdvancedConfigSectionProps> = ({
  projectId,
  narrationType,
}) => {
  const {
    items,
    selection,
    featureKey,
    setProjectSelection,
    createOrUpdateTemplate,
    deleteTemplate,
    renderPreview,
    getPromptDetail,
    loading,
    error,
    defaultCategory,
  } = usePrompts(projectId, narrationType || NarrationType.SHORT_DRAMA);

  const [newName, setNewName] = useState("");
  const [newTemplate, setNewTemplate] = useState("");
  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewKey, setPreviewKey] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [lastSelectedKey, setLastSelectedKey] = useState<string | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [templateModalMode, setTemplateModalMode] = useState<"create" | "edit">("create");
  const [copied, setCopied] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isCustomModalOpen, setIsCustomModalOpen] = useState(false);
  const [customInput, setCustomInput] = useState("");
  const [customError, setCustomError] = useState<string | null>(null);
  const { scriptLength, loading: scriptLengthLoading, saving: scriptLengthSaving, setScriptLengthAndPersist } =
    useProjectScriptLength(projectId);
  const {
    originalRatio,
    loading: originalRatioLoading,
    saving: originalRatioSaving,
    setOriginalRatioAndPersist,
  } = useProjectOriginalRatio(projectId);

  const currentSel = selection?.[featureKey];
  const selectedIdOrKey = lastSelectedKey || currentSel?.key_or_id || featureKey;
  const otherOfficialItems = (items || []).filter((it) => it.origin === "official" && it.id_or_key !== featureKey);

  const handleSelect = async (origin: "official" | "user", id_or_key: string) => {
    await setProjectSelection(origin, id_or_key);
    setLastSelectedKey(id_or_key);
  };

  const handleSaveTemplate = async () => {
    const payload: CreatePromptPayload = {
      name: newName.trim(),
      category: defaultCategory,
      template: newTemplate,
      enabled: true,
    };
    const d = await createOrUpdateTemplate({ ...payload, id: editingId || undefined });
    await setProjectSelection("user", d.id_or_key || (d as any).id);
    setLastSelectedKey(d.id_or_key || (d as any).id);
    setNewName("");
    setNewTemplate("");
    setEditingId(null);
    setIsTemplateModalOpen(false);
  };

  const handleRowPreview = async (id_or_key: string) => {
    if (previewKey === id_or_key && isPreviewOpen) {
      setIsPreviewOpen(false);
      setPreviewKey(null);
      setPreviewText(null);
      return;
    }
    setPreviewKey(id_or_key);
    setIsPreviewOpen(true);
    setPreviewText(null);
    try {
      const res = await renderPreview(id_or_key, {
        drama_name: "示例剧名",
        plot_analysis: "示例剧情分析",
        subtitle_content: "[00:00:01,000-00:00:03,000] 示例字幕",
      });
      const lines = res.messages.map((m) => `${m.role}: ${m.content}`);
      setPreviewText(lines.join("\n\n"));
    } catch (e: any) {
      setPreviewText(e?.message || "预览失败");
    }
  };

  const handleEditUserTemplate = async (id_or_key: string) => {
    try {
      const detail = await getPromptDetail(id_or_key);
      setEditingId(detail.id_or_key || id_or_key);
      setNewName(detail.name || "");
      setNewTemplate(detail.template || "");
      setLastSelectedKey(id_or_key);
      setTemplateModalMode("edit");
      setIsTemplateModalOpen(true);
    } catch (e: any) {
      setEditingId(id_or_key);
      setTemplateModalMode("edit");
      setIsTemplateModalOpen(true);
    }
  };

  const openDeleteModal = (id: string, name: string) => {
    setDeleteTarget({ id, name });
    setDeleteError(null);
    setIsDeleteModalOpen(true);
  };

  const closeDeleteModal = () => {
    if (deleteLoading) return;
    setIsDeleteModalOpen(false);
    setDeleteTarget(null);
    setDeleteError(null);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await deleteTemplate(deleteTarget.id);
      if (selectedIdOrKey === deleteTarget.id) {
        await setProjectSelection("official", featureKey);
        setLastSelectedKey(featureKey);
      }
      setIsDeleteModalOpen(false);
      setDeleteTarget(null);
    } catch (e: any) {
      setDeleteError(e?.message || "删除失败");
    } finally {
      setDeleteLoading(false);
    }
  };

  const handleCopyPreview = async () => {
    if (!previewText) return;
    try {
      await navigator.clipboard.writeText(previewText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.value = previewText;
      document.body.appendChild(textarea);
      textarea.select();
      try {
        document.execCommand("copy");
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } finally {
        document.body.removeChild(textarea);
      }
    }
  };

  const openCreateTemplateModal = () => {
    setEditingId(null);
    setNewName("");
    setNewTemplate("");
    setTemplateModalMode("create");
    setIsTemplateModalOpen(true);
  };

  const presetValues = SCRIPT_LENGTH_OPTIONS.map((opt) => opt.value);
  const isPresetSelected = presetValues.includes(scriptLength);
  const customSelectedRange = !isPresetSelected ? parseRangeFromString(scriptLength) : null;

  const openCustomModal = () => {
    setCustomError(null);
    if (customSelectedRange) {
      const avg = Math.round((customSelectedRange.min + customSelectedRange.max) / 2);
      setCustomInput(String(avg));
    } else {
      setCustomInput("40");
    }
    setIsCustomModalOpen(true);
  };

  const customNumber = Number.parseInt(customInput, 10);
  const customRange = Number.isFinite(customNumber) ? computeCustomRange(customNumber) : null;
  const customRangeText = customRange ? formatRangeTitle(customRange) : "";
  const customCallsText = customRange
    ? `预计约 ${estimateCallsForDisplay(customRange.max)} 次模型调用`
    : "";
  const canSaveCustom = Boolean(customRange);
  const customCardSubtitle = customSelectedRange
    ? `预计约 ${estimateCallsForDisplay(customSelectedRange.max)} 次模型调用`
    : "点击设置条数";

  return (
    <div className="border-gray-200 pt-4 space-y-3">
      <div className="border-t border-gray-200 pt-4">
        <div className="flex items-center justify-between">
          <label className="block text-sm font-medium text-gray-700 mb-2">解说脚本条数</label>
          {scriptLengthLoading ? (
            <span className="text-xs text-gray-500">加载中</span>
          ) : scriptLengthSaving ? (
            <span className="text-xs text-gray-500">保存中</span>
          ) : (
            <span className="text-xs text-gray-500">条数越多，生成更慢且消耗更高</span>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {SCRIPT_LENGTH_OPTIONS.map((opt) => {
            const isSelected = scriptLength === opt.value;
            return (
              <div
                key={opt.value}
                className={`
                relative flex flex-col justify-between p-3 rounded-lg border cursor-pointer transition-all duration-200
                ${
                  isSelected
                    ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                    : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                }
              `}
                onClick={() => void setScriptLengthAndPersist(opt.value)}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-sm font-medium ${isSelected ? "text-violet-900" : "text-gray-900"}`}>
                    {opt.title}
                  </span>
                  {isSelected && (
                    <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center">
                      <Check className="h-3 w-3 text-white" />
                    </div>
                  )}
                </div>
                <span className={`text-xs ${isSelected ? "text-violet-700" : "text-gray-500"}`}>{opt.subtitle}</span>
              </div>
            );
          })}
          {customSelectedRange ? (
            <div
              className={`
                relative flex flex-col justify-between p-3 rounded-lg border cursor-pointer transition-all duration-200
                ${
                  !isPresetSelected
                    ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                    : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                }
              `}
              onClick={() => void setScriptLengthAndPersist(formatRangeValue(customSelectedRange))}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-medium ${!isPresetSelected ? "text-violet-900" : "text-gray-900"}`}>
                  {formatRangeTitle(customSelectedRange)}
                </span>
                {!isPresetSelected ? (
                  <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center">
                    <Check className="h-3 w-3 text-white" />
                  </div>
                ) : null}
              </div>
              <span className={`text-xs ${!isPresetSelected ? "text-violet-700" : "text-gray-500"}`}>
                {customCardSubtitle}
              </span>
            </div>
          ) : null}
          <button
            type="button"
            onClick={openCustomModal}
            className="relative flex flex-col items-center justify-center p-3 rounded-lg border border-dashed border-violet-300 text-violet-600 bg-white hover:border-violet-500 hover:bg-violet-50 transition-all duration-200"
          >
            <Plus className="h-5 w-5 mb-1" />
            <span className="text-sm font-medium">自定义条数</span>
          </button>
        </div>
      </div>
      <div className="border-t border-gray-200 pt-4">
        <div className="flex items-center justify-between">
          <label className="block text-sm font-medium text-gray-700 mb-2">原片占比</label>
          {originalRatioLoading ? (
            <span className="text-xs text-gray-500">加载中</span>
          ) : originalRatioSaving ? (
            <span className="text-xs text-gray-500">保存中</span>
          ) : (
            <span className="text-xs text-gray-500">10% - 90%</span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <input
            type="range"
            min={ORIGINAL_RATIO_MIN}
            max={ORIGINAL_RATIO_MAX}
            step={1}
            value={originalRatio}
            onChange={(e) => void setOriginalRatioAndPersist(Number(e.target.value))}
            className="flex-1"
          />
          <div className="text-sm text-gray-800 w-28">
            <div>{originalRatio}%</div>
            <div className="text-gray-500">{`解说 ${100 - originalRatio}%`}</div>
          </div>
        </div>
        <div className="text-xs text-gray-500 mt-2">滑动时自动保存</div>
      </div>
      <div className="border-gray-200">
        <div className="flex items-center justify-between">
          <label className="block text-sm font-medium text-gray-700 mb-2">{`提示词选择（${narrationType || NarrationType.SHORT_DRAMA}）`}</label>
          {loading ? <span className="text-xs text-gray-500">加载中</span> : null}
        </div>
        {error ? <div className="text-xs text-red-600 mb-2">{error}</div> : null}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {/* Official Default */}
          <div
            className={`
                relative flex flex-col p-3 rounded-lg border cursor-pointer transition-all duration-200 min-h-[80px]
                ${
                  selectedIdOrKey === featureKey
                    ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                    : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                }
             `}
            onClick={() => handleSelect("official", featureKey)}
          >
            <div className="flex items-center justify-between mb-2">
              <span
                className={`text-sm font-medium ${selectedIdOrKey === featureKey ? "text-violet-900" : "text-gray-900"}`}
              >
                官方默认模板
              </span>
              {selectedIdOrKey === featureKey && (
                <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center">
                  <Check className="h-3 w-3 text-white" />
                </div>
              )}
            </div>
            <div className="mt-auto flex justify-end">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleRowPreview(featureKey);
                }}
                className="text-xs text-blue-600 hover:underline"
              >
                预览
              </button>
            </div>
          </div>

          {/* Other Official Items */}
          {otherOfficialItems.map((it) => {
            const isSelected = selectedIdOrKey === it.id_or_key;
            return (
              <div
                key={it.id_or_key}
                className={`
                  relative flex flex-col p-3 rounded-lg border cursor-pointer transition-all duration-200 min-h-[80px]
                  ${
                    isSelected
                      ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                      : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                  }
                `}
                onClick={() => handleSelect("official", it.id_or_key)}
              >
                <div className="flex items-center justify-between mb-2">
                  <span
                    className={`text-sm font-medium truncate ${isSelected ? "text-violet-900" : "text-gray-900"}`}
                    title={it.name}
                  >
                    {it.name}
                  </span>
                  {isSelected && (
                    <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center">
                      <Check className="h-3 w-3 text-white" />
                    </div>
                  )}
                </div>
                <div className="mt-auto flex justify-end">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRowPreview(it.id_or_key);
                    }}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    预览
                  </button>
                </div>
              </div>
            );
          })}

          {/* User Items */}
          {items
            .filter((it) => it.origin === "user")
            .map((it) => {
              const isSelected = selectedIdOrKey === it.id_or_key;
              return (
                <div
                  key={it.id_or_key}
                  className={`
                  relative flex flex-col p-3 rounded-lg border cursor-pointer transition-all duration-200 min-h-[80px]
                  ${
                    isSelected
                      ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                      : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                  }
                `}
                  onClick={() => handleSelect("user", it.id_or_key)}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2 overflow-hidden">
                      <span className="text-[10px] px-1.5 py-0.5 bg-yellow-50 text-yellow-600 rounded border border-yellow-200 whitespace-nowrap">
                        自定义
                      </span>
                      <span
                        className={`text-sm font-medium truncate ${isSelected ? "text-violet-900" : "text-gray-900"}`}
                        title={it.name}
                      >
                        {it.name}
                      </span>
                    </div>
                    {isSelected && (
                      <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center shrink-0 ml-2">
                        <Check className="h-3 w-3 text-white" />
                      </div>
                    )}
                  </div>
                  <div className="mt-auto flex justify-end space-x-3" onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => handleRowPreview(it.id_or_key)}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      预览
                    </button>
                    <button
                      onClick={() => handleEditUserTemplate(it.id_or_key)}
                      className="text-xs text-gray-600 hover:underline hover:text-gray-900"
                    >
                      编辑
                    </button>
                    <button
                      onClick={() => openDeleteModal(it.id_or_key, it.name)}
                      className="h-6 w-6 flex items-center justify-center rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                      title="删除"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          <button
            type="button"
            onClick={openCreateTemplateModal}
            className="relative flex flex-col items-center justify-center p-3 rounded-lg border border-dashed border-violet-300 text-violet-600 bg-white hover:border-violet-500 hover:bg-violet-50 transition-all duration-200 min-h-[80px]"
          >
            <Plus className="h-5 w-5 mb-1" />
            <span className="text-sm font-medium">新建自定义模板</span>
          </button>
        </div>
      </div>

      {isPreviewOpen ? (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div
            className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
            onClick={() => {
              setIsPreviewOpen(false);
              setPreviewText(null);
              setPreviewKey(null);
            }}
          />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div className="relative bg-white rounded-lg shadow-xl w-[70%]">
              <div className="flex items-center justify-between p-4 border-b border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900">预览</h3>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={handleCopyPreview}
                    disabled={!previewText}
                    className="flex items-center px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {copied ? (
                      <>
                        <Check className="h-4 w-4 mr-1" />
                        已复制
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4 mr-1" />
                        复制
                      </>
                    )}
                  </button>
                  <button
                    onClick={() => {
                      setIsPreviewOpen(false);
                      setPreviewText(null);
                      setPreviewKey(null);
                    }}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>
              </div>
              <div className="p-4">
                <div className="max-h-[70vh] overflow-auto">
                  <pre className="text-xs bg-white border rounded p-2 whitespace-pre-wrap">{previewText || "加载中..."}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {isTemplateModalOpen ? (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div
            className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
            onClick={() => setIsTemplateModalOpen(false)}
          />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div className="relative bg-white rounded-lg shadow-xl w-[70%]">
              <div className="flex items-center justify-between p-6 border-b border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900">{templateModalMode === "edit" ? "编辑自定义模板" : "新建自定义模板"}</h3>
                <button onClick={() => setIsTemplateModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6 space-y-2">
                <input
                  type="text"
                  placeholder="模板名称"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                />
                <textarea
                  placeholder={`模版需要要求大模型输出包含这些字段，不然无法合并：_id, timestamp, picture, narration, OST`}
                  value={newTemplate}
                  onChange={(e) => setNewTemplate(e.target.value)}
                  className="w-full h-[60vh] border border-gray-300 rounded px-3 py-2 text-sm"
                />
                <div className="flex items-center justify-end space-x-3 pt-2">
                  <button onClick={() => setIsTemplateModalOpen(false)} className="px-3 py-1 text-gray-700 bg-gray-100 rounded text-sm">取消</button>
                  <button
                    onClick={handleSaveTemplate}
                    disabled={!newName.trim() || !newTemplate.trim()}
                    className="px-3 py-1 bg-violet-600 text-white rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >保存并使用</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {isCustomModalOpen ? (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div
            className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
            onClick={() => setIsCustomModalOpen(false)}
          />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="flex items-center justify-between p-6 border-b border-gray-200">
                <h3 className="text-lg font-semibold text-gray-900">自定义条数范围</h3>
                <button onClick={() => setIsCustomModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                  <X className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6 space-y-3">
                <div className="text-sm text-gray-600">输入目标条数，系统会自动生成一个合理范围</div>
                <input
                  type="number"
                  min={CUSTOM_SCRIPT_LENGTH_MIN}
                  max={CUSTOM_SCRIPT_LENGTH_MAX}
                  value={customInput}
                  onChange={(e) => {
                    setCustomInput(e.target.value);
                    setCustomError(null);
                  }}
                  placeholder={`建议 ${CUSTOM_SCRIPT_LENGTH_MIN}-${CUSTOM_SCRIPT_LENGTH_MAX}`}
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
                />
                {customError ? <div className="text-xs text-red-600">{customError}</div> : null}
                {customRange ? (
                  <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700 space-y-1">
                    <div>默认范围：{customRangeText}</div>
                    <div>{customCallsText}</div>
                  </div>
                ) : (
                  <div className="text-xs text-gray-500">请输入 {CUSTOM_SCRIPT_LENGTH_MIN}-{CUSTOM_SCRIPT_LENGTH_MAX} 的数字</div>
                )}
                <div className="flex items-center justify-end space-x-3 pt-2">
                  <button
                    onClick={() => setIsCustomModalOpen(false)}
                    className="px-3 py-1 text-gray-700 bg-gray-100 rounded text-sm"
                  >
                    取消
                  </button>
                  <button
                    onClick={async () => {
                      if (!customRange) {
                        setCustomError(`请输入 ${CUSTOM_SCRIPT_LENGTH_MIN}-${CUSTOM_SCRIPT_LENGTH_MAX} 的数字`);
                        return;
                      }
                      await setScriptLengthAndPersist(formatRangeValue(customRange));
                      setIsCustomModalOpen(false);
                    }}
                    disabled={!canSaveCustom}
                    className="px-3 py-1 bg-violet-600 text-white rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    保存并使用
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {isDeleteModalOpen ? (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={closeDeleteModal} />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
              <div className="flex items-center justify-between p-6 border-b border-gray-200">
                <div className="flex items-center space-x-3">
                  <div className="flex items-center justify-center w-10 h-10 bg-red-100 rounded-lg">
                    <Trash2 className="h-5 w-5 text-red-600" />
                  </div>
                  <h3 className="text-xl font-semibold text-gray-900">确认删除</h3>
                </div>
                <button
                  onClick={closeDeleteModal}
                  disabled={deleteLoading}
                  className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
                >
                  <X className="h-6 w-6" />
                </button>
              </div>
              <div className="p-6">
                {deleteError ? (
                  <div className="bg-red-50 text-red-600 px-4 py-3 rounded-lg text-sm mb-4">{deleteError}</div>
                ) : null}
                <p className="text-gray-700 mb-4">
                  确定要删除自定义提示词{" "}
                  <span className="font-semibold">"{deleteTarget?.name || ""}"</span> 吗？
                </p>
                <p className="text-sm text-red-600">此操作不可撤销。</p>
              </div>
              <div className="bg-gray-50 px-6 py-4 flex items-center justify-end space-x-3 border-t border-gray-200">
                <button
                  type="button"
                  onClick={closeDeleteModal}
                  disabled={deleteLoading}
                  className="px-4 py-2 text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg font-medium transition-colors disabled:opacity-50"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleConfirmDelete}
                  disabled={deleteLoading}
                  className="px-6 py-2 bg-red-600 text-white rounded-lg font-medium hover:bg-red-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {deleteLoading ? "删除中..." : "确认删除"}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default GenerateAdvancedConfigSection;
