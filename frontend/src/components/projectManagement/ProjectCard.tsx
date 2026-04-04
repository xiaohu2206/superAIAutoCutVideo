// 项目卡片组件

import {
  Calendar,
  CheckCircle,
  Clock,
  Edit,
  FileText,
  MoreHorizontal,
  Trash2,
  XCircle,
  Eye,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
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
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }

    const handleClickOutside = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [menuOpen]);

  /**
   * 获取状态样式
   */
  const getStatusConfig = (status: ProjectStatus) => {
    const configs = {
      [ProjectStatus.DRAFT]: {
        icon: Edit,
        label: "草稿",
        color: "text-gray-600",
        bg: "bg-gray-100",
      },
      [ProjectStatus.PROCESSING]: {
        icon: Clock,
        label: "处理中",
        color: "text-blue-600",
        bg: "bg-blue-100",
      },
      [ProjectStatus.COMPLETED]: {
        icon: CheckCircle,
        label: "已完成",
        color: "text-green-600",
        bg: "bg-green-100",
      },
      [ProjectStatus.FAILED]: {
        icon: XCircle,
        label: "失败",
        color: "text-red-600",
        bg: "bg-red-100",
      },
    };
    return configs[status] || configs[ProjectStatus.DRAFT];
  };

  const statusConfig = getStatusConfig(project.status);
  const StatusIcon = statusConfig.icon;

  /**
   * 项目类型标签
   */
  const getTypeConfig = (type?: string) => {
    if (type === "visual") {
      return {
        icon: Eye,
        label: "视觉推理",
        color: "text-purple-700",
        bg: "bg-purple-100",
      };
    }
    return {
      icon: FileText,
      label: "字幕推理",
      color: "text-amber-700",
      bg: "bg-amber-100",
    };
  };
  const typeConfig = getTypeConfig(project.project_type);
  const TypeIcon = typeConfig.icon;

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
    <div
      className="group relative flex h-full cursor-pointer flex-col overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-lg"
      onClick={() => onEdit(project)}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onEdit(project);
        }
      }}
    >

      <div className="flex flex-1 flex-col p-5">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex items-start gap-2">
              <h3 className="line-clamp-2 flex-1 text-base font-semibold leading-6 text-gray-900">
                {project.name}
              </h3>
              <div className="relative flex-shrink-0" ref={menuRef}>
                <button
                  type="button"
                  aria-label="更多操作"
                  aria-expanded={menuOpen}
                  onClick={(event) => {
                    event.stopPropagation();
                    setMenuOpen((prev) => !prev);
                  }}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-transparent text-gray-400 transition-colors hover:border-gray-200 hover:bg-gray-100 hover:text-gray-700"
                >
                  <MoreHorizontal className="h-4 w-4" />
                </button>

                {menuOpen && (
                  <div className="absolute right-0 top-10 z-10 w-32 overflow-hidden rounded-xl border border-gray-200 bg-white py-1 shadow-lg">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setMenuOpen(false);
                        onEdit(project);
                      }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-blue-50 hover:text-blue-700"
                    >
                      <Edit className="h-4 w-4" />
                      编辑
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setMenuOpen(false);
                        onDelete(project);
                      }}
                      className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 transition-colors hover:bg-red-50"
                    >
                      <Trash2 className="h-4 w-4" />
                      删除
                    </button>
                  </div>
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium ${statusConfig.bg} ${statusConfig.color}`}
              >
                <StatusIcon className="mr-1 h-3.5 w-3.5" />
                {statusConfig.label}
              </span>
              <div className="flex items-center text-xs text-gray-500">
                <Calendar className="mr-1 h-3.5 w-3.5 text-gray-400" />
                <span>{formatDate(project.created_at)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* {project.description ? (
          <p className="mb-4 line-clamp-2 min-h-[2.75rem] text-sm leading-5 text-gray-500">
            {project.description}
          </p>
        ) : (
          <div className="mb-4 min-h-[2.75rem] rounded-xl border border-dashed border-gray-200 bg-gray-50/80 px-3 py-2 text-sm text-gray-400">
            暂无项目描述
          </div>
        )} */}

        <div className="mt-auto flex flex-wrap gap-2">
          <div
            className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-medium ${typeConfig.bg} ${typeConfig.color}`}
          >
            <TypeIcon className="mr-1.5 h-3.5 w-3.5" />
            <span className="truncate">{typeConfig.label}</span>
          </div>

          <div className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600">
            <FileText className="mr-1.5 h-3.5 w-3.5 text-gray-400" />
            <span className="truncate">{project.narration_type}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProjectCard;
