import { useEffect, useState } from "react";
import { TauriCommands } from "../services/tauriService";

let cachedAppVersion: string | null = null;
let pendingFetch: Promise<string> | null = null;

function extractVersion(info: Record<string, string> | null | undefined) {
  const raw = info && (info as any).version;
  const v = typeof raw === "string" ? raw.trim() : "";
  return v;
}

async function fetchAppVersionOnce(): Promise<string> {
  if (cachedAppVersion) return cachedAppVersion;
  if (!pendingFetch) {
    pendingFetch = (async () => {
      const info = await TauriCommands.getAppInfo();
      const v = extractVersion(info);
      cachedAppVersion = v || "";
      return cachedAppVersion;
    })().finally(() => {
      pendingFetch = null;
    });
  }
  return pendingFetch;
}

export function useAppVersion() {
  const [appVersion, setAppVersion] = useState<string>(cachedAppVersion || "");

  useEffect(() => {
    let active = true;
    const load = async () => {
      const v = await fetchAppVersionOnce();
      if (!active) return;
      setAppVersion(v);
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  return { appVersion };
}
