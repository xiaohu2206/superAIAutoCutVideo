import React, { useEffect, useState } from "react";
import { TauriCommands } from "@/services/tauriService";
import { FolderOpen, File } from "lucide-react";

const FilePickerDemo: React.FC = () => {
  const [dir, setDir] = useState<string>("");
  const [filePath, setFilePath] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isTauri, setIsTauri] = useState<boolean>(false);

  useEffect(() => {
    const detect = () => {
      const w: any = typeof window !== "undefined" ? window : undefined;
      const hasIpc = typeof w?.__TAURI_IPC__ === "function";
      const hasCoreInvoke = !!w?.__TAURI__?.core?.invoke;
      const hasMeta = !!w?.__TAURI_METADATA__ || !!w?.__TAURI_INTERNALS__;
      return hasIpc || hasCoreInvoke || hasMeta;
    };
    const initial = detect();
    setIsTauri(initial);
    if (!initial) {
      let tries = 0;
      const timer = setInterval(() => {
        tries += 1;
        const ok = detect();
        if (ok || tries >= 10) {
          setIsTauri(ok);
          clearInterval(timer);
        }
      }, 300);
      return () => clearInterval(timer);
    }
  }, []);

  const pickDir = async () => {
    setError(null);
    try {
      const res = await TauriCommands.selectOutputDirectory();
      if (!res.cancelled && res.path) setDir(res.path);
    } catch (e: any) {
      setError(e?.message || "选择目录失败");
    }
  };

  const pickFile = async () => {
    setError(null);
    try {
      const res = await TauriCommands.selectVideoFile();
      if (!res.cancelled && res.path) setFilePath(res.path);
    } catch (e: any) {
      setError(e?.message || "选择文件失败");
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <FolderOpen className="h-5 w-5 text-blue-600 mr-2" />
            <span className="text-lg font-medium text-gray-900">选择目录</span>
          </div>
          <button
            onClick={pickDir}
            className="px-3 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700"
          >
            浏览
          </button>
        </div>
        <div className="text-sm text-gray-600">
          已选: {dir || "未选择"}
        </div>
      </div>

      <div className="bg-white rounded-lg p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <File className="h-5 w-5 text-blue-600 mr-2" />
            <span className="text-lg font-medium text-gray-900">选择文件</span>
          </div>
          <button
            onClick={pickFile}
            className="px-3 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700"
          >
            浏览
          </button>
        </div>
        <div className="text-sm text-gray-600">
          已选: {filePath || "未选择"}
        </div>
      </div>

      {error ? <div className="text-sm text-red-600">{error}</div> : null}

      <div className="text-xs text-gray-500">
        运行环境: {isTauri ? "Tauri" : "浏览器"}
      </div>
    </div>
  );
};

export default FilePickerDemo;
