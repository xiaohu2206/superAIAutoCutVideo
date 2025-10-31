import React from "react";
import type { AppSettings } from "../types";

interface BackendSettingsProps {
  settings: AppSettings;
  updateSetting: (path: string, value: any) => void;
}

/**
 * 后端设置组件
 */
export const BackendSettings: React.FC<BackendSettingsProps> = ({
  settings,
  updateSetting,
}) => {
  return (
    <div className="space-y-6">
      <div>
        <label className="flex items-center">
          <input
            type="checkbox"
            checked={settings.backend.autoStart}
            onChange={(e) =>
              updateSetting("backend.autoStart", e.target.checked)
            }
            className="mr-3"
          />
          <span className="text-sm font-medium text-gray-700">
            应用启动时自动启动后端服务
          </span>
        </label>
        <p className="text-xs text-gray-500 mt-1">
          启用后，应用启动时会自动启动Python后端服务
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          后端端口
        </label>
        <input
          type="number"
          min="1000"
          max="65535"
          value={settings.backend.port}
          onChange={(e) =>
            updateSetting("backend.port", Number(e.target.value))
          }
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">
          后端服务监听的端口号 (1000-65535)
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          连接超时 (秒)
        </label>
        <input
          type="number"
          min="5"
          max="300"
          value={settings.backend.timeout}
          onChange={(e) =>
            updateSetting("backend.timeout", Number(e.target.value))
          }
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">连接后端服务的超时时间</p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">
          最大重试次数
        </label>
        <input
          type="number"
          min="0"
          max="10"
          value={settings.backend.maxRetries}
          onChange={(e) =>
            updateSetting("backend.maxRetries", Number(e.target.value))
          }
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="text-xs text-gray-500 mt-1">连接失败时的最大重试次数</p>
      </div>
    </div>
  );
};

