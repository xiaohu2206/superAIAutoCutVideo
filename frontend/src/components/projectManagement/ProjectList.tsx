import { FolderOpen, LayoutGrid, List, SearchX } from "lucide-react";
import React, { useState } from "react";
import type { Project } from "../../types/project";
import ProjectCard from "./ProjectCard";

interface ProjectListProps {
  projects: Project[];
  loading: boolean;
  onEdit: (project: Project) => void;
  onDelete: (project: Project) => void;
  searchQuery?: string;
}

const ProjectList: React.FC<ProjectListProps> = ({
  projects,
  loading,
  onEdit,
  onDelete,
  searchQuery = "",
}) => {
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  if (loading) {
    return (
      <div className="flex h-full min-h-0 flex-col pb-3">
        <div className="project-list-scrollbar min-h-0 flex-1 overflow-y-auto">
          <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-2.5">
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((i) => (
              <div
                key={i}
                className="project-list-card h-[95px] overflow-hidden rounded-md border border-slate-200/80 bg-white/95 shadow-sm"
              >
                <div className="flex h-full animate-pulse flex-col px-3 py-2.5">
                  <div className="h-3.5 w-3/4 rounded bg-slate-200 dark:bg-white/10" />
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <div className="h-3 w-24 rounded bg-slate-200 dark:bg-white/10" />
                    <div className="h-5 w-12 rounded-full bg-slate-200 dark:bg-white/10" />
                  </div>
                  <div className="mt-auto flex items-center justify-between border-t border-slate-200/70 pt-2 dark:border-white/[0.06]">
                    <div className="h-3 w-20 rounded bg-slate-200 dark:bg-white/10" />
                    <div className="h-3 w-5 rounded bg-slate-200 dark:bg-white/10" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (projects.length === 0) {
    const isSearching = searchQuery.trim().length > 0;
    const EmptyIcon = isSearching ? SearchX : FolderOpen;

    return (
      <div className="flex h-full min-h-[240px] flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white/70 px-6 py-12 text-center dark:border-[#333333] dark:bg-[#1f1f1f]/70">
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-lg bg-slate-100 text-slate-500 dark:bg-white/10 dark:text-zinc-400">
          <EmptyIcon className="h-7 w-7" aria-hidden />
        </div>
        <h3 className="text-base font-semibold text-gray-900 dark:text-zinc-100">
          {isSearching ? "没有匹配的项目" : "暂无项目"}
        </h3>
        <p className="mt-2 max-w-md text-sm leading-6 text-gray-500 dark:text-zinc-400">
          {isSearching
            ? "换一个关键词试试，或清空搜索查看全部项目。"
            : "从上方选择一种解说类型，即可创建第一个视频剪辑项目。"}
        </p>
      </div>
    );
  }

  const sortedProjects = [...projects].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <div className="flex h-full min-h-0 flex-col pb-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-950 dark:text-zinc-100">最近项目</h3>
        <div className="flex items-center gap-5">
          <div className="project-view-switch inline-flex h-7 items-stretch overflow-hidden rounded-lg border border-slate-200/80 bg-white/85 p-0.5 shadow-sm">
            <button
              type="button"
              title="网格视图"
              onClick={() => setViewMode("grid")}
              data-active={viewMode === "grid"}
              className="project-view-switch__btn flex h-6 w-10 items-center justify-center rounded-md text-xs transition-colors data-[active=true]:bg-blue-50 data-[active=true]:text-blue-600 data-[active=true]:shadow-sm data-[active=false]:text-slate-500 hover:data-[active=false]:bg-slate-50"
            >
              <LayoutGrid className="h-4 w-4" aria-hidden />
            </button>
            <span className="project-view-switch__divider" aria-hidden />
            <button
              type="button"
              title="列表视图"
              onClick={() => setViewMode("list")}
              data-active={viewMode === "list"}
              className="project-view-switch__btn flex h-6 w-10 items-center justify-center rounded-md text-xs transition-colors data-[active=true]:bg-blue-50 data-[active=true]:text-blue-600 data-[active=true]:shadow-sm data-[active=false]:text-slate-500 hover:data-[active=false]:bg-slate-50"
            >
              <List className="h-4 w-4" aria-hidden />
            </button>
          </div>
        </div>
      </div>
      <div className="project-list-scrollbar min-h-0 flex-1 overflow-y-auto">
        <div
          className={
            viewMode === "grid"
              ? "grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-2.5"
              : "grid grid-cols-1 gap-2.5"
          }
        >
          {sortedProjects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              onEdit={onEdit}
              onDelete={onDelete}
            />
          ))}
        </div>
      </div>
    </div>
  );
};

export default ProjectList;
