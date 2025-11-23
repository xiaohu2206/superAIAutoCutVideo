// 项目卡片组件

import React from "react";
import {
  Folder,
  Calendar,
  FileText,
  Trash2,
  Clock,
  CheckCircle,
  XCircle,
  Edit,
} from "lucide-react";
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
    <div className="bg-white rounded-lg shadow-md hover:shadow-lg transition-shadow duration-200 overflow-hidden">
      {/* 卡片内容 */}
      <div className="p-6">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center space-x-3">
            <div className="flex items-center justify-center w-12 h-12 bg-blue-100 rounded-lg">
              <Folder className="h-6 w-6 text-blue-600" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-900 line-clamp-1">
                {project.name}
              </h3>
              <div className="flex items-center mt-1">
                <span
                  className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${statusConfig.bg} ${statusConfig.color}`}
                >
                  <StatusIcon className="h-3 w-3 mr-1" />
                  {statusConfig.label}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* 项目描述 */}
        {project.description && (
          <p className="text-sm text-gray-600 mb-4 line-clamp-2">
            {project.description}
          </p>
        )}

        {/* 项目信息 */}
        <div className="space-y-2">
          {/* 解说类型 */}
          <div className="flex items-center text-sm text-gray-600">
            <FileText className="h-4 w-4 mr-2 text-gray-400" />
            <span>{project.narration_type}</span>
          </div>

          {/* 视频文件 */}
          {/* {project.video_path && (
            <div className="flex items-center text-sm text-gray-600">
              <Video className="h-4 w-4 mr-2 text-gray-400" />
              <span className="truncate">
                {project.video_current_name || project.video_path.split("/").pop() || "视频文件"}
              </span>
            </div>
          )} */}

          {/* 创建时间 */}
          <div className="flex items-center text-sm text-gray-600">
            <Calendar className="h-4 w-4 mr-2 text-gray-400" />
            <span>{formatDate(project.created_at)}</span>
          </div>
        </div>
      </div>

      {/* 分隔线 */}
      <div className="h-px bg-gray-100" />

      {/* 卡片底部操作栏 */}
      <div className="bg-gray-50 px-6 py-4 flex items-center justify-between border-t border-gray-200">
        <button
          onClick={() => onEdit(project)}
          className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          <Edit className="h-4 w-4 mr-2" />
          编辑项目
        </button>

        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete(project);
          }}
          className="flex items-center px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg text-sm font-medium transition-colors"
        >
          <Trash2 className="h-4 w-4 mr-2" />
          删除
        </button>
      </div>
    </div>
  );
};

export default ProjectCard;
