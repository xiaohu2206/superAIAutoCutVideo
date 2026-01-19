// 项目卡片组件

import {
  Calendar,
  CheckCircle,
  Clock,
  Edit,
  FileText,
  Folder,
  Trash2,
  XCircle,
} from "lucide-react";
import React from "react";
import type { Project } from "../../types/project";
import { ProjectStatus } from "../../types/project";

interface ProjectCardProps {
  project: Project;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
}

/**
 * 项目卡片组件
 */
const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  onEdit,
  onDelete,
}) => {
  /**
   * 获取状态样式
   */
  const getStatusConfig = (status: ProjectStatus) => {
    const configs = {
      [ProjectStatus.DRAFT]: {
        icon: Edit,
        label: "草稿",
        color: "text-gray-500",
        bg: "bg-gray-100",
      },
      [ProjectStatus.PROCESSING]: {
        icon: Clock,
        label: "处理中",
        color: "text-blue-500",
        bg: "bg-blue-100",
      },
      [ProjectStatus.COMPLETED]: {
        icon: CheckCircle,
        label: "已完成",
        color: "text-green-500",
        bg: "bg-green-100",
      },
      [ProjectStatus.FAILED]: {
        icon: XCircle,
        label: "失败",
        color: "text-red-500",
        bg: "bg-red-100",
      },
    };
    return configs[status] || configs[ProjectStatus.DRAFT];
  };

  const statusConfig = getStatusConfig(project.status);
  const StatusIcon = statusConfig.icon;

  /**
   * 格式化日期
   */
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow duration-200 overflow-hidden border border-gray-100 flex flex-col h-full">
      {/* 卡片内容 */}
      <div className="p-4 flex-1">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center space-x-3 w-full">
            <div className="flex items-center justify-center w-10 h-10 bg-blue-50 rounded-lg flex-shrink-0">
              <Folder className="h-5 w-5 text-blue-600" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold text-gray-900 truncate mr-2">
                  {project.name}
                </h3>
                <span
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium flex-shrink-0 ${statusConfig.bg} ${statusConfig.color}`}
                >
                  <StatusIcon className="h-3 w-3 mr-1" />
                  {statusConfig.label}
                </span>
              </div>
              <div className="flex items-center mt-1 text-xs text-gray-500">
                <Calendar className="h-3 w-3 mr-1 text-gray-400" />
                <span>{formatDate(project.created_at)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* 项目描述 */}
        {project.description && (
          <p className="text-xs text-gray-500 mb-3 line-clamp-2 h-8">
            {project.description}
          </p>
        )}

        {/* 项目信息 */}
        <div className="space-y-1">
          {/* 解说类型 */}
          <div className="flex items-center text-xs text-gray-600 bg-gray-50 rounded px-2 py-1">
            <FileText className="h-3 w-3 mr-2 text-gray-400" />
            <span className="truncate">{project.narration_type}</span>
          </div>
        </div>
      </div>

      {/* 卡片底部操作栏 */}
      <div className="bg-gray-50 px-3 py-2 flex items-center justify-between border-t border-gray-100 gap-2">
        <button
          onClick={() => onEdit(project)}
          // className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
          className="bg-blue-600 flex-1 flex items-center text-white  justify-center px-3 py-1.5 border border-gray-200 rounded text-xs font-medium hover:bg-blue-700 hover:border-blue-300  transition-colors"
        >
          <Edit className="h-3 w-3 mr-1.5" />
          编辑
        </button>

        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(project);
          }}
          className="flex items-center justify-center px-3 py-1.5 text-red-600 hover:bg-red-50 rounded text-xs font-medium transition-colors"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
};

export default ProjectCard;
