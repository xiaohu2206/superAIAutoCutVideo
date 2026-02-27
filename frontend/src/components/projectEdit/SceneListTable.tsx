import React, { useState } from "react";
import { Play, Eye, X } from "lucide-react";
import { SceneResult } from "../../types/scene";

interface SceneListTableProps {
  sceneResult: SceneResult | null;
  onPlayScene: (start: number, end: number) => void;
}

const SceneListTable: React.FC<SceneListTableProps> = ({ sceneResult, onPlayScene }) => {
  const [isModalOpen, setIsModalOpen] = useState(false);

  if (!sceneResult || !sceneResult.scenes || sceneResult.scenes.length === 0) {
    return null;
  }

  const renderVision = (vision: any): string => {
    if (!vision) return "";
    if (typeof vision === "string") return vision;
    if (Array.isArray(vision)) {
      const parts = vision
        .map((seg) => {
          const st = typeof seg?.start_time === "number" ? seg.start_time.toFixed(2) : "";
          const et = typeof seg?.end_time === "number" ? seg.end_time.toFixed(2) : "";
          const txt = typeof seg?.text === "string" ? seg.text.trim() : "";
          if (!txt) return "";
          return st && et ? `[${st}-${et}] ${txt}` : txt;
        })
        .filter(Boolean);
      return parts.join("；");
    }
    return "";
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">视觉分析结果</h2>
      </div>

      <p className="text-sm text-gray-600">
        点击下方区域可查看详细视觉分析结果。
      </p>

      <div 
        className="relative group cursor-pointer"
        onClick={() => setIsModalOpen(true)}
      >
        <div className="w-full h-10 px-4 py-2 font-mono text-sm border border-gray-300 rounded-lg bg-gray-50 overflow-hidden text-gray-700 hover:border-blue-400 hover:ring-1 hover:ring-blue-400 transition-all flex items-center justify-between">
          <span>共 {sceneResult.scenes.length} 个镜头</span>
          <span className="text-gray-500 text-xs">总帧数: {sceneResult.total_frames} (FPS: {sceneResult.fps})</span>
        </div>
        
        <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-5 flex items-center justify-center transition-all rounded-lg pointer-events-none">
           <div className="opacity-0 group-hover:opacity-100 bg-white shadow-sm border border-gray-200 px-3 py-1.5 rounded-full text-sm font-medium text-gray-700 flex items-center">
             <Eye className="w-3 h-3 mr-1.5" />
             查看详情
           </div>
        </div>

        <div className="absolute top-2 right-2 bg-gray-100 px-2 py-1 rounded text-xs text-gray-600 hidden group-hover:block">
           点击展开
        </div>
      </div>

      {/* Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto">
          <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" onClick={() => setIsModalOpen(false)} />
          <div className="flex items-center justify-center min-h-screen p-4">
            <div className="relative bg-white rounded-lg shadow-xl max-w-6xl w-full flex flex-col max-h-[90vh]">
              {/* Header */}
              <div className="flex items-center justify-between p-6 border-b border-gray-200 bg-white rounded-t-lg sticky top-0 z-10">
                <div className="flex items-center gap-4">
                  <h3 className="text-xl font-semibold text-gray-900">视觉分析详情</h3>
                  <div className="text-sm text-gray-500 bg-gray-100 px-2 py-1 rounded">
                    共 {sceneResult.scenes.length} 个镜头 | 总帧数: {sceneResult.total_frames} | FPS: {sceneResult.fps}
                  </div>
                </div>
                <button 
                  onClick={() => setIsModalOpen(false)}
                  className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded hover:bg-gray-100"
                >
                  <X className="h-6 w-6" />
                </button>
              </div>

              {/* Table Header */}
              <div className="bg-gray-50 px-6 py-3 border-b border-gray-200 font-medium text-sm text-gray-700 grid grid-cols-12 gap-4 sticky top-0 z-0">
                <div className="col-span-1">序号</div>
                <div className="col-span-2">操作</div>
                <div className="col-span-2">时间段</div>
                <div className="col-span-3">对应字幕</div>
                <div className="col-span-4">视觉分析</div>
              </div>

              {/* Table Content */}
              <div className="overflow-y-auto p-0 flex-1 bg-white">
                {sceneResult.scenes.map((scene) => (
                  <div 
                    key={scene.id} 
                    className="px-6 py-3 border-b border-gray-100 text-sm text-gray-600 grid grid-cols-12 gap-4 items-center hover:bg-blue-50 transition-colors"
                  >
                    <div className="col-span-1 font-medium text-gray-900">{scene.id}</div>
                    <div className="col-span-2">
                        <button 
                            onClick={() => onPlayScene(scene.start_time, scene.end_time)}
                            className="flex items-center text-blue-600 hover:text-blue-800 transition-colors bg-blue-50 hover:bg-blue-100 px-2 py-1 rounded-md text-xs font-medium border border-blue-200"
                        >
                            <Play className="w-3 h-3 mr-1 fill-current" />
                            播放镜头
                        </button>
                    </div>
                    <div className="col-span-2 font-mono text-xs bg-gray-100 px-2 py-1 rounded inline-block text-center w-fit text-gray-700">
                      {scene.time_range}
                    </div>
                    <div className="col-span-3 truncate text-gray-800" title={scene.subtitle}>
                      {scene.subtitle || <span className="text-gray-400 italic">无</span>}
                    </div>
                    <div className="col-span-4 text-gray-800 text-xs line-clamp-3 leading-relaxed" title={renderVision(scene.vision)}>
                      {renderVision(scene.vision) || <span className="text-gray-400 italic">—</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};


export default SceneListTable;
