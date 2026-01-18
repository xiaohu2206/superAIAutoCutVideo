import { Check, Copy, X } from "lucide-react";
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
  { value: "15～20条", title: "15～20 条", subtitle: "预计最少 1 次模型调用" },
  { value: "30～40条", title: "30～40 条", subtitle: "预计最少 3 次模型调用" },
  { value: "40～60条", title: "40～60 条", subtitle: "预计最少 4 次模型调用" },
  { value: "60～80条", title: "60～80 条", subtitle: "预计最少 5 次模型调用" },
  { value: "80～100条", title: "80～100 条", subtitle: "预计最少 6 次模型调用" },
];

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
  return DEFAULT_SCRIPT_LENGTH;
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
  const { scriptLength, loading: scriptLengthLoading, saving: scriptLengthSaving, setScriptLengthAndPersist } =
    useProjectScriptLength(projectId);

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
        <div className="space-y-2">
          {SCRIPT_LENGTH_OPTIONS.map((opt) => (
            <div
              key={opt.value}
              className="flex items-center justify-between bg-gray-50 p-2 rounded cursor-pointer"
              onClick={() => void setScriptLengthAndPersist(opt.value)}
            >
              <label className="flex items-center space-x-2">
                <input
                  type="radio"
                  name="script-length"
                  checked={scriptLength === opt.value}
                  onChange={() => void setScriptLengthAndPersist(opt.value)}
                />
                <span className="text-sm">{opt.title}</span>
              </label>
              <span className="text-xs text-gray-500">{opt.subtitle}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="border-gray-200">
        <div className="flex items-center justify-between">
          <label className="block text-sm font-medium text-gray-700 mb-2">{`提示词选择（${narrationType || NarrationType.SHORT_DRAMA}）`}</label>
          {loading ? <span className="text-xs text-gray-500">加载中</span> : null}
        </div>
        {error ? <div className="text-xs text-red-600 mb-2">{error}</div> : null}
        <div className="space-y-2">
          <div className="flex items-center justify-between bg-gray-50 p-2 rounded cursor-pointer" onClick={() => handleSelect("official", featureKey)}>
            <label className="flex items-center space-x-2">
              <input
                type="radio"
                name="prompt-select"
                checked={selectedIdOrKey === featureKey}
                onChange={() => handleSelect("official", featureKey)}
              />
              <span className="text-sm">官方默认模板</span>
            </label>
            <button onClick={(e) => { e.stopPropagation(); handleRowPreview(featureKey); }} className="text-xs text-blue-600">预览</button>
          </div>
          {otherOfficialItems.map((it) => (
            <div key={it.id_or_key} className="flex items-center justify-between bg-gray-50 p-2 rounded cursor-pointer" onClick={() => handleSelect("official", it.id_or_key)}>
              <label className="flex items-center space-x-2">
                <input
                  type="radio"
                  name="prompt-select"
                  checked={selectedIdOrKey === it.id_or_key}
                  onChange={() => handleSelect("official", it.id_or_key)}
                />
                <span className="text-sm">{it.name}</span>
              </label>
              <button onClick={(e) => { e.stopPropagation(); handleRowPreview(it.id_or_key); }} className="text-xs text-blue-600">预览</button>
            </div>
          ))}
          {items.filter((it) => it.origin === "user").map((it) => (
            <div key={it.id_or_key} className="flex items-center justify-between bg-gray-50 p-2 rounded cursor-pointer" onClick={() => handleSelect("user", it.id_or_key)}>
              <label className="flex items-center space-x-2">
                <input
                  type="radio"
                  name="prompt-select"
                  checked={selectedIdOrKey === it.id_or_key}
                  onChange={() => handleSelect("user", it.id_or_key)}
                />
                <span className="text-sm">{it.name}</span>
              </label>
              <div className="flex items-center space-x-2" onClick={(e) => e.stopPropagation()}>
                <button onClick={() => handleRowPreview(it.id_or_key)} className="text-xs text-blue-600">预览</button>
                <button onClick={() => handleEditUserTemplate(it.id_or_key)} className="text-xs text-gray-600">编辑</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-gray-200 pt-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">自定义提示词</label>
        <div className="space-y-2">
          <button onClick={openCreateTemplateModal} className="px-3 py-1 bg-violet-600 text-white rounded text-sm">新建自定义模板</button>
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
    </div>
  );
};

export default GenerateAdvancedConfigSection;
