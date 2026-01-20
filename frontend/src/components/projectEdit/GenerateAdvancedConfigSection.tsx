import React, { useState } from "react";
import { usePrompts } from "../../hooks/usePrompts";
import { NarrationType } from "../../types/project";
import type { CreatePromptPayload } from "../../types/prompts";
import CustomScriptLengthModal from "./advancedConfig/CustomScriptLengthModal";
import DeleteConfirmModal from "./advancedConfig/DeleteConfirmModal";
import { useProjectOriginalRatio, useProjectScriptLength, useProjectScriptLanguage } from "./advancedConfig/hooks";
import OriginalRatioSlider from "./advancedConfig/OriginalRatioSlider";
import PreviewModal from "./advancedConfig/PreviewModal";
import PromptTemplateList from "./advancedConfig/PromptTemplateList";
import ScriptLengthSelector from "./advancedConfig/ScriptLengthSelector";
import TemplateModal from "./advancedConfig/TemplateModal";
import { parseRangeFromString, SCRIPT_LENGTH_OPTIONS } from "./advancedConfig/utils";
import ScriptLanguageSelector from "./advancedConfig/ScriptLanguageSelector";

interface GenerateAdvancedConfigSectionProps {
  projectId: string;
  narrationType?: NarrationType;
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
  const { scriptLength, loading: scriptLengthLoading, saving: scriptLengthSaving, setScriptLengthAndPersist } =
    useProjectScriptLength(projectId);
  const {
    originalRatio,
    loading: originalRatioLoading,
    saving: originalRatioSaving,
    setOriginalRatioAndPersist,
  } = useProjectOriginalRatio(projectId);
  const {
    scriptLanguage,
    loading: scriptLanguageLoading,
    saving: scriptLanguageSaving,
    setScriptLanguageAndPersist,
  } = useProjectScriptLanguage(projectId);

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
    setIsCustomModalOpen(true);
  };


  return (
    <div className="border-gray-200 pt-4 space-y-3">
      <ScriptLengthSelector
        scriptLength={scriptLength}
        loading={scriptLengthLoading}
        saving={scriptLengthSaving}
        setScriptLengthAndPersist={setScriptLengthAndPersist}
        onOpenCustomModal={openCustomModal}
      />
      <OriginalRatioSlider
        originalRatio={originalRatio}
        loading={originalRatioLoading}
        saving={originalRatioSaving}
        setOriginalRatioAndPersist={setOriginalRatioAndPersist}
      />
      <ScriptLanguageSelector
        scriptLanguage={scriptLanguage}
        loading={scriptLanguageLoading}
        saving={scriptLanguageSaving}
        setScriptLanguageAndPersist={setScriptLanguageAndPersist}
      />
      {error ? <div className="text-xs text-red-600 mb-2">{error}</div> : null}
      <PromptTemplateList
        narrationType={narrationType}
        featureKey={featureKey}
        selectedIdOrKey={selectedIdOrKey}
        items={(items || []) as any}
        otherOfficialItems={otherOfficialItems as any}
        onSelect={(origin, id_or_key) => void handleSelect(origin, id_or_key)}
        onPreview={(id_or_key) => void handleRowPreview(id_or_key)}
        onEditUserTemplate={(id_or_key) => void handleEditUserTemplate(id_or_key)}
        onDeleteUserTemplate={(id, name) => void openDeleteModal(id, name)}
        onCreateTemplate={openCreateTemplateModal}
      />
      <PreviewModal
        isOpen={isPreviewOpen}
        text={previewText}
        copied={copied}
        onCopy={handleCopyPreview}
        onClose={() => {
          setIsPreviewOpen(false);
          setPreviewText(null);
          setPreviewKey(null);
        }}
      />
      <TemplateModal
        isOpen={isTemplateModalOpen}
        mode={templateModalMode}
        name={newName}
        template={newTemplate}
        onChangeName={setNewName}
        onChangeTemplate={setNewTemplate}
        onSave={handleSaveTemplate}
        onClose={() => setIsTemplateModalOpen(false)}
      />
      <CustomScriptLengthModal
        isOpen={isCustomModalOpen}
        onClose={() => setIsCustomModalOpen(false)}
        initialRange={customSelectedRange}
        onSave={(v) => setScriptLengthAndPersist(v)}
      />
      <DeleteConfirmModal
        isOpen={isDeleteModalOpen}
        loading={deleteLoading}
        error={deleteError}
        targetName={deleteTarget?.name || null}
        onConfirm={handleConfirmDelete}
        onClose={closeDeleteModal}
      />
    </div>
  );
};

export default GenerateAdvancedConfigSection;
