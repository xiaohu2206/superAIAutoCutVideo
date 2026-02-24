import React from "react";
import CopywritingSection from "./CopywritingSection";
import ScriptJsonEditor from "./ScriptJsonEditor";

interface ScriptEditorProps {
  editedCopywriting: string;
  setEditedCopywriting: (copywriting: string) => void;
  isSavingCopywriting: boolean;
  handleSaveCopywriting: (content?: string) => void;
  editedScript: string;
  setEditedScript: (script: string) => void;
  isSaving: boolean;
  handleSaveScript: () => void;
}

const ScriptEditor: React.FC<ScriptEditorProps> = ({
  editedCopywriting,
  setEditedCopywriting,
  isSavingCopywriting,
  handleSaveCopywriting,
  editedScript,
  setEditedScript,
  isSaving,
  handleSaveScript,
}) => {
  return (
    <div className="bg-white rounded-lg shadow-md p-6 space-y-8">
      <CopywritingSection
        editedCopywriting={editedCopywriting}
        setEditedCopywriting={setEditedCopywriting}
        isSavingCopywriting={isSavingCopywriting}
        handleSaveCopywriting={handleSaveCopywriting}
      />

      <hr className="border-gray-200" />

      <ScriptJsonEditor
        editedScript={editedScript}
        setEditedScript={setEditedScript}
        isSaving={isSaving}
        handleSaveScript={handleSaveScript}
      />
    </div>
  );
};

export default ScriptEditor;
