import {
  Calendar,
  CheckCircle2,
  Clapperboard,
  Clock3,
  Edit3,
  Eye,
  FileText,
  Film,
  Mic,
  MoreHorizontal,
  Mountain,
  Music2,
  PenLine,
  Trash2,
  Trophy,
  Tv2,
  XCircle,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import type { Project } from "../../types/project";
import { NarrationType } from "../../types/project";
import { ProjectStatus } from "../../types/project";

interface ProjectCardProps {
  project: Project;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
}

const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  onEdit,
  onDelete,
}) => {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;

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

  const getStatusConfig = (status: ProjectStatus) => {
    const configs = {
      [ProjectStatus.DRAFT]: {
        icon: PenLine,
        label: "草稿",
        className: "border-blue-100 bg-blue-50 text-blue-600 dark:border-blue-400/20 dark:bg-blue-500/10 dark:text-blue-300",
      },
      [ProjectStatus.PROCESSING]: {
        icon: Clock3,
        label: "处理中",
        className: "border-amber-100 bg-amber-50 text-amber-600 dark:border-amber-400/20 dark:bg-amber-500/10 dark:text-amber-300",
      },
      [ProjectStatus.COMPLETED]: {
        icon: CheckCircle2,
        label: "已完成",
        className: "border-emerald-100 bg-emerald-50 text-emerald-600 dark:border-emerald-400/20 dark:bg-emerald-500/10 dark:text-emerald-300",
      },
      [ProjectStatus.FAILED]: {
        icon: XCircle,
        label: "失败",
        className: "border-rose-100 bg-rose-50 text-rose-600 dark:border-rose-400/20 dark:bg-rose-500/10 dark:text-rose-300",
      },
    };
    return configs[status] || configs[ProjectStatus.DRAFT];
  };

  const getTypeConfig = (type?: string) => {
    if (type === "omni") {
      return {
        icon: Eye,
        label: "全感知推理",
        iconClassName: "text-fuchsia-600",
      };
    }
    if (type === "visual") {
      return {
        icon: Eye,
        label: "视觉推理",
        iconClassName: "text-violet-600",
      };
    }
    return {
      icon: FileText,
      label: "字幕推理",
      iconClassName: "text-amber-600",
    };
  };

  const getNarrationTypeConfig = (type?: NarrationType) => {
    const configs = {
      [NarrationType.MOVIE]: {
        icon: Film,
        iconClassName: "text-blue-600",
      },
      [NarrationType.TV_DRAMA]: {
        icon: Tv2,
        iconClassName: "text-violet-600",
      },
      [NarrationType.SHORT_DRAMA]: {
        icon: Clapperboard,
        iconClassName: "text-rose-600",
      },
      [NarrationType.VARIETY]: {
        icon: Music2,
        iconClassName: "text-orange-500",
      },
      [NarrationType.DOCUMENTARY]: {
        icon: Mountain,
        iconClassName: "text-emerald-600",
      },
      [NarrationType.SPORTS]: {
        icon: Trophy,
        iconClassName: "text-orange-500",
      },
      [NarrationType.GENERAL]: {
        icon: Mic,
        iconClassName: "text-sky-600",
      },
    };
    return configs[type || NarrationType.GENERAL] || configs[NarrationType.GENERAL];
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return "未知时间";

    return date.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const statusConfig = getStatusConfig(project.status);
  const typeConfig = getTypeConfig(project.project_type);
  const narrationTypeConfig = getNarrationTypeConfig(project.narration_type);
  const StatusIcon = statusConfig.icon;
  const TypeIcon = typeConfig.icon;
  const NarrationTypeIcon = narrationTypeConfig.icon;

  return (
    <article
      className="group relative flex h-full min-h-[112px] cursor-pointer flex-col overflow-hidden rounded-md border border-slate-200 bg-white shadow-sm transition-colors hover:border-blue-200 hover:shadow-md focus-within:border-blue-300 dark:border-white/10 dark:bg-[#1f1f1f] dark:hover:border-blue-400/30 dark:hover:bg-[#242424] dark:hover:shadow-black/30 dark:focus-within:border-blue-400/40"
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
      <div className="flex flex-1 flex-col px-4 py-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1 pr-8">
            <h3 className="line-clamp-2 text-sm font-semibold leading-5 text-slate-950 dark:text-zinc-100">
              {project.name}
            </h3>
            <div className="mt-1 flex items-center text-[11px] text-slate-500 dark:text-zinc-400">
              <Calendar className="mr-1 h-3 w-3 text-slate-400 dark:text-zinc-500" />
              <span className="truncate">{formatDate(project.created_at)}</span>
            </div>
          </div>

          <div className="relative shrink-0" ref={menuRef}>
            <button
              type="button"
              aria-label="更多操作"
              aria-expanded={menuOpen}
              onClick={(event) => {
                event.stopPropagation();
                setMenuOpen((prev) => !prev);
              }}
              className="flex h-5 w-6 items-center justify-center rounded border border-transparent text-slate-500 transition-colors hover:border-slate-200 hover:bg-slate-50 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-100 dark:text-zinc-400 dark:hover:border-white/10 dark:hover:bg-white/10 dark:hover:text-zinc-100 dark:focus:ring-blue-500/30"
            >
              <MoreHorizontal className="h-4 w-4" />
            </button>

            {menuOpen && (
              <div className="absolute right-0 top-6 z-10 w-32 overflow-hidden rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-white/10 dark:bg-[#242424] dark:shadow-black/40">
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    setMenuOpen(false);
                    onEdit(project);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-gray-700 transition-colors hover:bg-blue-50 hover:text-blue-700 dark:text-zinc-200 dark:hover:bg-blue-500/10 dark:hover:text-blue-300"
                >
                  <Edit3 className="h-4 w-4" />
                  编辑
                </button>
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    setMenuOpen(false);
                    onDelete(project);
                  }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-sm text-red-600 transition-colors hover:bg-red-50 hover:text-red-700 dark:text-rose-300 dark:hover:bg-rose-500/10 dark:hover:text-rose-200"
                >
                  <Trash2 className="h-4 w-4" />
                  删除
                </button>
              </div>
            )}
          </div>
        </div>


        <div className="mt-auto pt-3">
          <div className="absolute right-4 bottom-9">
            <span
              className={`inline-flex max-w-[96px] items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${statusConfig.className}`}
            >
              <StatusIcon className="mr-1 h-3 w-3 shrink-0" />
              <span className="truncate">{statusConfig.label}</span>
            </span>
          </div>

          <div className="flex min-w-0 items-center gap-3 text-[11px] text-slate-500 dark:text-zinc-400">
            <div className="flex min-w-0 flex-1 items-center gap-1.5">
              <TypeIcon className={`h-3.5 w-3.5 shrink-0 ${typeConfig.iconClassName}`} />
              <span className="truncate">
                {typeConfig.label}
              </span>
            </div>
            <div className="h-3 w-px shrink-0 bg-slate-200 dark:bg-white/10" />
            <div className="flex min-w-0 flex-1 items-center gap-1.5">
              <NarrationTypeIcon className={`h-3.5 w-3.5 shrink-0 ${narrationTypeConfig.iconClassName}`} />
              <span className="truncate">
                {project.narration_type}
              </span>
            </div>
          </div>
        </div>
      </div>
    </article>
  );
};

export default ProjectCard;
