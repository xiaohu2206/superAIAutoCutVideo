import React from "react";
import { useProjectOriginalRatio, useProjectScriptLanguage, useProjectInterleaveMode } from "./hooks";
import OriginalRatioSlider from "./OriginalRatioSlider";
import ScriptLanguageSelector from "./ScriptLanguageSelector";

interface VideoGenAdvancedConfigProps {
  projectId: string;
}

const VideoGenAdvancedConfig: React.FC<VideoGenAdvancedConfigProps> = ({
  projectId,
}) => {
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
  const {
    interleaveMode,
    loading: interleaveModeLoading,
    saving: interleaveModeSaving,
    setInterleaveModeAndPersist,
  } = useProjectInterleaveMode(projectId);

  return (
    <div className="border-gray-200 pt-4 space-y-3">
      <OriginalRatioSlider
        interleaveMode={interleaveMode}
        interleaveModeLoading={interleaveModeLoading}
        interleaveModeSaving={interleaveModeSaving}
        setInterleaveModeAndPersist={setInterleaveModeAndPersist}
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
    </div>
  );
};

export default VideoGenAdvancedConfig;
