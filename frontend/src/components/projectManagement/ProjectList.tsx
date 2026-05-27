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
      <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3 pb-3">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div
            key={i}
            className="min-h-[112px] overflow-hidden rounded-md border border-gray-200 bg-white shadow-sm"
          >
            <div className="animate-pulse p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1 space-y-2">
                  <div className="h-4 w-3/4 rounded bg-gray-200" />
                  <div className="h-3 w-1/2 rounded bg-gray-200" />
                </div>
                <div className="h-5 w-6 rounded bg-gray-200" />
              </div>
              <div className="mt-5 flex gap-2">
                <div className="h-3 w-16 rounded bg-gray-200" />
                <div className="h-3 w-20 rounded bg-gray-200" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (projects.length === 0) {
    const isSearching = searchQuery.trim().length > 0;
    const EmptyIcon = isSearching ? SearchX : FolderOpen;

    return (
      <div className="flex min-h-[240px] flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white/70 px-6 py-12 text-center">
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-lg bg-slate-100 text-slate-500">
          <EmptyIcon className="h-7 w-7" aria-hidden />
        </div>
        <h3 className="text-base font-semibold text-gray-900">
          {isSearching ? "没有匹配的项目" : "暂无项目"}
        </h3>
        <p className="mt-2 max-w-md text-sm leading-6 text-gray-500">
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
    <div className="pb-3">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-950">最近项目</h3>
        <div className="flex items-center gap-4">
          <div className="inline-flex h-8 overflow-hidden rounded-md border border-slate-200 bg-white p-0.5 shadow-sm">
            <button
              type="button"
              title="网格视图"
              onClick={() => setViewMode("grid")}
              className={`flex h-7 w-8 items-center justify-center rounded text-xs transition-colors ${
                viewMode === "grid"
                  ? "bg-blue-50 text-blue-600"
                  : "text-slate-500 hover:bg-slate-50"
              }`}
            >
              <LayoutGrid className="h-4 w-4" aria-hidden />
            </button>
            <button
              type="button"
              title="列表视图"
              onClick={() => setViewMode("list")}
              className={`flex h-7 w-8 items-center justify-center rounded text-xs transition-colors ${
                viewMode === "list"
                  ? "bg-blue-50 text-blue-600"
                  : "text-slate-500 hover:bg-slate-50"
              }`}
            >
              <List className="h-4 w-4" aria-hidden />
            </button>
          </div>
          <span className="whitespace-nowrap text-xs text-slate-500">
            共 {sortedProjects.length} 个项目
          </span>
        </div>
      </div>
      <div
        className={
          viewMode === "grid"
            ? "grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3"
            : "grid grid-cols-1 gap-3"
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
  );
};

export default ProjectList;
