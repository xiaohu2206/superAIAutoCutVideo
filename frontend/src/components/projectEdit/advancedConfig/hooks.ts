import { useCallback, useEffect, useRef, useState } from "react";
import { projectService } from "../../../services/projectService";
import type { ScriptLengthOption } from "../../../types/project";
import { normalizeOriginalRatio, normalizeOriginalRatioSelection, normalizeScriptLength } from "./utils";

export function useProjectCopywritingWordCount(projectId: string): {
  copywritingWordCount: number | null;
  loading: boolean;
  saving: boolean;
  setCopywritingWordCountAndPersist: (value: number | null) => Promise<void>;
} {
  const [copywritingWordCount, setCopywritingWordCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveSeqRef = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = await projectService.getProject(projectId);
      setCopywritingWordCount(p?.copywriting_word_count ?? null);
    } catch {
      void 0;
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setCopywritingWordCountAndPersist = useCallback(
    async (value: number | null) => {
      setCopywritingWordCount(value);
      const seq = ++saveSeqRef.current;
      setSaving(true);
      try {
        await projectService.updateProjectQueued(projectId, { copywriting_word_count: value });
      } catch {
        void 0;
      } finally {
        if (saveSeqRef.current === seq) setSaving(false);
      }
    },
    [projectId]
  );

  return { copywritingWordCount, loading, saving, setCopywritingWordCountAndPersist };
}

export function useProjectScriptLength(projectId: string): {
  scriptLength: ScriptLengthOption;
  loading: boolean;
  saving: boolean;
  setScriptLengthAndPersist: (value: ScriptLengthOption) => Promise<void>;
} {
  const [scriptLength, setScriptLength] = useState<ScriptLengthOption>("auto");
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

export function useProjectOriginalRatio(projectId: string): {
  originalRatio: number | null;
  loading: boolean;
  saving: boolean;
  setOriginalRatioAndPersist: (value: number | null) => Promise<void>;
} {
  const [originalRatio, setOriginalRatio] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveSeqRef = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = await projectService.getProject(projectId);
      const normalized = normalizeOriginalRatioSelection(p?.original_ratio);
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
    async (value: number | null) => {
      const normalized = value === null ? null : normalizeOriginalRatio(value);
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

export function useProjectScriptLanguage(projectId: string): {
  scriptLanguage: "zh" | "en";
  loading: boolean;
  saving: boolean;
  setScriptLanguageAndPersist: (value: "zh" | "en") => Promise<void>;
} {
  const [scriptLanguage, setScriptLanguage] = useState<"zh" | "en">("zh");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const saveSeqRef = useRef(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = await projectService.getProject(projectId);
      const v = (p?.script_language as any) as "zh" | "en";
      if (v === "en" || v === "zh") {
        setScriptLanguage(v);
      } else {
        const seq = ++saveSeqRef.current;
        setSaving(true);
        try {
          await projectService.updateProjectQueued(projectId, { script_language: "zh" });
        } catch {
          void 0;
        } finally {
          if (saveSeqRef.current === seq) setSaving(false);
        }
        setScriptLanguage("zh");
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

  const setScriptLanguageAndPersist = useCallback(
    async (value: "zh" | "en") => {
      setScriptLanguage(value);
      const seq = ++saveSeqRef.current;
      setSaving(true);
      try {
        await projectService.updateProjectQueued(projectId, { script_language: value });
      } catch {
        void 0;
      } finally {
        if (saveSeqRef.current === seq) setSaving(false);
      }
    },
    [projectId]
  );

  return { scriptLanguage, loading, saving, setScriptLanguageAndPersist };
}
