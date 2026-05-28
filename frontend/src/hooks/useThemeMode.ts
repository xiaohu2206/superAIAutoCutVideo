import { useEffect, useState } from "react";

export type ThemeMode = "light" | "dark";

const readThemeMode = (): ThemeMode => {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
};

/** 与 App.tsx 中 html.dark 同步，用于在组件内选择完整主题 token（避免 JS 内 dark: 类名不可靠） */
export function useThemeMode(): ThemeMode {
  const [mode, setMode] = useState<ThemeMode>(readThemeMode);

  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setMode(readThemeMode());
    sync();

    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return mode;
}
