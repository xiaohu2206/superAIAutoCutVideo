import type { LucideIcon } from "lucide-react";
import {
  Clapperboard,
  Edit3,
  Film,
  Mic,
  MoreHorizontal,
  Mountain,
  Music2,
  Trash2,
  Trophy,
  Tv2,
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
    const configs: Record<ProjectStatus, { label: string; className: string }> = {
      [ProjectStatus.DRAFT]: {
        label: "草稿",
        className: "border-blue-200 bg-blue-50 text-blue-600 dark:border-blue-400/30 dark:bg-blue-500/15 dark:text-blue-300",
      },
      [ProjectStatus.PROCESSING]: {
        label: "处理中",
        className: "border-amber-200 bg-amber-50 text-amber-600 dark:border-amber-400/30 dark:bg-amber-500/15 dark:text-amber-300",
      },
      [ProjectStatus.COMPLETED]: {
        label: "已完成",
        className: "border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-400/30 dark:bg-emerald-500/15 dark:text-emerald-300",
      },
      [ProjectStatus.FAILED]: {
        label: "失败",
        className: "border-rose-200 bg-rose-50 text-rose-600 dark:border-rose-400/30 dark:bg-rose-500/15 dark:text-rose-300",
      },
    };
    return configs[status] || configs[ProjectStatus.DRAFT];
  };

  const getNarrationTypeConfig = (type?: NarrationType) => {
    const configs: Record<
      NarrationType,
      { icon: LucideIcon; label: string; iconClassName: string }
    > = {
      [NarrationType.MOVIE]: {
        icon: Film,
        label: NarrationType.MOVIE,
        iconClassName: "text-blue-500 dark:text-blue-400",
      },
      [NarrationType.TV_DRAMA]: {
        icon: Tv2,
        label: NarrationType.TV_DRAMA,
        iconClassName: "text-violet-500 dark:text-violet-400",
      },
      [NarrationType.SHORT_DRAMA]: {
        icon: Clapperboard,
        label: NarrationType.SHORT_DRAMA,
        iconClassName: "text-rose-500 dark:text-rose-400",
      },
      [NarrationType.VARIETY]: {
        icon: Music2,
        label: NarrationType.VARIETY,
        iconClassName: "text-orange-500 dark:text-orange-400",
      },
      [NarrationType.DOCUMENTARY]: {
        icon: Mountain,
        label: NarrationType.DOCUMENTARY,
        iconClassName: "text-emerald-500 dark:text-emerald-400",
      },
      [NarrationType.SPORTS]: {
        icon: Trophy,
        label: NarrationType.SPORTS,
        iconClassName: "text-amber-500 dark:text-amber-400",
      },
      [NarrationType.GENERAL]: {
        icon: Mic,
        label: NarrationType.GENERAL,
        iconClassName: "text-sky-500 dark:text-sky-400",
      },
    };
    return configs[type || NarrationType.GENERAL] || configs[NarrationType.GENERAL];
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return "未知时间";

    const pad = (value: number) => value.toString().padStart(2, "0");
    return `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };

  const statusConfig = getStatusConfig(project.status);
  const narrationTypeConfig = getNarrationTypeConfig(project.narration_type);
  const NarrationTypeIcon = narrationTypeConfig.icon;

  return (
    <article
      className="project-list-card group relative flex h-[95px] cursor-pointer flex-col rounded-md  bg-white/95 shadow-sm transition-all duration-200 hover:border-blue-200 hover:bg-white hover:shadow-md focus-within:border-blue-300 focus-within:ring-2 focus-within:ring-blue-100 dark:focus-within:ring-blue-500/20"
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
      <div className="flex h-full flex-col px-3 py-2.5">
        <div className="min-w-0">
          <h3 className="truncate text-[13px] font-semibold leading-5 text-slate-950 dark:text-zinc-100" title={project.name}>
            {project.name}
          </h3>
          <div className="mt-1 mb-1 flex min-w-0 items-center justify-between gap-2">
            <div className="flex min-w-0 items-center text-[10px] leading-none text-slate-500 dark:text-zinc-400">
              <span className="truncate">{formatDate(project.created_at)}</span>
            </div>
            <span
              className={`inline-flex h-5 max-w-[72px] shrink-0 items-center rounded-full border px-2 text-[10px] font-medium leading-none ${statusConfig.className}`}
            >
              <span className="truncate">{statusConfig.label}</span>
            </span>
          </div>
        </div>

        <div className="mt-auto flex items-center justify-between gap-2 border-t border-slate-100 pt-2 dark:border-white/[0.06]">
          <div className="flex min-w-0 items-center gap-1.5 text-[11px] leading-none text-slate-500 dark:text-zinc-400">
            <NarrationTypeIcon className={`h-3.5 w-3.5 shrink-0 ${narrationTypeConfig.iconClassName}`} />
            <span className="truncate">{narrationTypeConfig.label}</span>
          </div>

          <div className="relative shrink-0 self-center" ref={menuRef}>
            <button
              type="button"
              aria-label="更多操作"
              aria-expanded={menuOpen}
              onClick={(event) => {
                event.stopPropagation();
                setMenuOpen((prev) => !prev);
              }}
              className="flex h-5 w-7 items-center justify-center rounded-md border border-transparent text-slate-500 transition-colors hover:border-slate-200 hover:bg-slate-50 hover:text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-100 dark:text-zinc-400 dark:hover:border-white/10 dark:hover:bg-white/[0.08] dark:hover:text-zinc-100 dark:focus:ring-blue-500/30"
            >
              <MoreHorizontal className="h-4 w-4" />
            </button>

            {menuOpen && (
              <div className="absolute bottom-7 right-0 z-20 w-32 overflow-hidden rounded-lg border border-gray-200 bg-white py-1 shadow-lg dark:border-[#2a2a2a] dark:bg-[#242424] dark:shadow-black/40">
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
      </div>
    </article>
  );
};

export default ProjectCard;
