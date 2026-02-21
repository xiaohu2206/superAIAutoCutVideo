import React from "react";
import { Play } from "lucide-react";
import { SceneResult } from "../../types/scene";

interface SceneListTableProps {
  sceneResult: SceneResult | null;
  onPlayScene: (start: number, end: number) => void;
}

const SceneListTable: React.FC<SceneListTableProps> = ({ sceneResult, onPlayScene }) => {
  if (!sceneResult || !sceneResult.scenes || sceneResult.scenes.length === 0) {
    return null;
  }

  return (
    <div className="mt-4 border border-gray-200 rounded-lg overflow-hidden bg-white shadow-sm">
      <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 font-medium text-sm text-gray-700 grid grid-cols-12 gap-4">
        <div className="col-span-1">序号</div>
        <div className="col-span-2">操作</div>
        <div className="col-span-3">时间段</div>
        <div className="col-span-6">对应字幕</div>
      </div>
      <div className="max-h-[400px] overflow-y-auto">
        {sceneResult.scenes.map((scene) => (
          <div 
            key={scene.id} 
            className="px-4 py-3 border-b border-gray-100 text-sm text-gray-600 grid grid-cols-12 gap-4 items-center hover:bg-blue-50 transition-colors"
          >
            <div className="col-span-1 font-medium">{scene.id}</div>
            <div className="col-span-2">
                <button 
                    onClick={() => onPlayScene(scene.start_time, scene.end_time)}
                    className="flex items-center text-blue-600 hover:text-blue-800 transition-colors bg-blue-50 hover:bg-blue-100 px-2 py-1 rounded-md text-xs font-medium"
                >
                    <Play className="w-3 h-3 mr-1 fill-current" />
                    播放镜头
                </button>
            </div>
            <div className="col-span-3 font-mono text-xs bg-gray-100 px-2 py-1 rounded inline-block text-center w-fit">
              {scene.time_range}
            </div>
            <div className="col-span-6 truncate text-gray-800" title={scene.subtitle}>
              {scene.subtitle || <span className="text-gray-400 italic">无</span>}
            </div>
          </div>
        ))}
      </div>
      <div className="px-4 py-2 bg-gray-50 border-t border-gray-200 text-xs text-gray-500 flex justify-between">
        <span>共 {sceneResult.scenes.length} 个镜头</span>
        <span>总帧数: {sceneResult.total_frames} (FPS: {sceneResult.fps})</span>
      </div>
    </div>
  );
};

export default SceneListTable;
