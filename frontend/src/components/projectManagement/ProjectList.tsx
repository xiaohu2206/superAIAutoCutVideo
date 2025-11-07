// 项目列表组件

import React from "react";
import { FolderOpen } from "lucide-react";
import ProjectCard from "./ProjectCard";
import type { Project } from "../../types/project";

interface ProjectListProps {
  projects: Project[];
  loading: boolean;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
}

/**
 * 项目列表组件
 */
const ProjectList: React.FC<ProjectListProps> = ({
  projects,
  loading,
  onEdit,
  onDelete,
}) => {
  // 加载状态
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-white rounded-lg shadow-md overflow-hidden animate-pulse"
          >
            <div className="p-6 space-y-4">
              <div className="flex items-center space-x-3">
                <div className="w-12 h-12 bg-gray-200 rounded-lg" />
                <div className="flex-1 space-y-2">
                  <div className="h-5 bg-gray-200 rounded w-3/4" />
                  <div className="h-4 bg-gray-200 rounded w-1/2" />
                </div>
              </div>
              <div className="space-y-2">
                <div className="h-4 bg-gray-200 rounded" />
                <div className="h-4 bg-gray-200 rounded w-5/6" />
              </div>
            </div>
            <div className="bg-gray-50 px-6 py-4 border-t border-gray-200">
              <div className="h-9 bg-gray-200 rounded" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  // 空状态
  if (projects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <div className="flex items-center justify-center w-20 h-20 bg-gray-100 rounded-full mb-4">
          <FolderOpen className="h-10 w-10 text-gray-400" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">暂无项目</h3>
        <p className="text-gray-500 text-center max-w-md">
          点击上方"创建项目"按钮开始创建您的第一个视频剪辑项目
        </p>
      </div>
    );
  }

  // 项目列表
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      {projects.map((project) => (
        <ProjectCard
          key={project.id}
          project={project}
          onEdit={onEdit}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
};

export default ProjectList;
