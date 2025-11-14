import { Info } from "lucide-react";
import React from "react";

const AboutSection: React.FC = () => (
  <div className="max-w-4xl mx-auto space-y-6">
    <div className="bg-white rounded-lg p-6">
      <div className="flex items-center mb-6">
        <Info className="h-6 w-6 text-blue-600 mr-3" />
        <h2 className="text-2xl font-bold text-gray-900">关于应用</h2>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h3 className="text-lg font-medium text-gray-900 mb-3">应用信息</h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-600">应用名称:</dt>
              <dd className="font-medium">SuperAI智能视频剪辑</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-600">版本:</dt>
              <dd className="font-medium">1.0.0</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-600">构建时间:</dt>
              <dd className="font-medium">{new Date().toLocaleDateString("zh-CN")}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-600">开发者:</dt>
              <dd className="font-medium">xiaohu2206 Team</dd>
            </div>
          </dl>
        </div>

        <div>
          <h3 className="text-lg font-medium text-gray-900 mb-3">技术栈</h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center">
              <div className="w-2 h-2 bg-blue-500 rounded-full mr-2" />
              <span>React 18 + TypeScript</span>
            </div>
            <div className="flex items-center">
              <div className="w-2 h-2 bg-green-500 rounded-full mr-2" />
              <span>Tauri (Rust)</span>
            </div>
            <div className="flex items-center">
              <div className="w-2 h-2 bg-yellow-500 rounded-full mr-2" />
              <span>Python FastAPI</span>
            </div>
            <div className="flex items-center">
              <div className="w-2 h-2 bg-purple-500 rounded-full mr-2" />
              <span>TailwindCSS</span>
            </div>
            <div className="flex items-center">
              <div className="w-2 h-2 bg-red-500 rounded-full mr-2" />
              <span>OpenCV + FFmpeg</span>
            </div>
          </div>
        </div>
      </div>

    </div>
  </div>
);

export default AboutSection;