import { Folder } from "lucide-react";
import React from "react";
import type { AppSettings } from "../../types";

interface PathSettingsProps {
  settings: AppSettings;
  updateSetting: (path: string, value: any) => void;
  selectDirectory: (settingPath: string) => void;
}

/**
 * 路径设置组件
 */
export const PathSettings: React.FC<PathSettingsProps> = ({
  settings,
  updateSetting,
  selectDirectory,
}) => {
  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          默认输入目录
        </label>
        <div className="flex space-x-2">
          <input
            type="text"
            value={settings.paths.defaultInputDir}
            onChange={(e) =>
              updateSetting("paths.defaultInputDir", e.target.value)
            }
            placeholder="选择默认的视频输入目录"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={() => selectDirectory("paths.defaultInputDir")}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
          >
            <Folder className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          默认输出目录
        </label>
        <div className="flex space-x-2">
          <input
            type="text"
            value={settings.paths.defaultOutputDir}
            onChange={(e) =>
              updateSetting("paths.defaultOutputDir", e.target.value)
            }
            placeholder="选择默认的视频输出目录"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={() => selectDirectory("paths.defaultOutputDir")}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
          >
            <Folder className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          临时文件目录
        </label>
        <div className="flex space-x-2">
          <input
            type="text"
            value={settings.paths.tempDir}
            onChange={(e) => updateSetting("paths.tempDir", e.target.value)}
            placeholder="选择临时文件存储目录"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            onClick={() => selectDirectory("paths.tempDir")}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200 transition-colors"
          >
            <Folder className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

