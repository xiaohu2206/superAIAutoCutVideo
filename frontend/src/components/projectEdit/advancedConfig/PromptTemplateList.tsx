import { Check, Trash2 } from "lucide-react";
import React from "react";
import { NarrationType } from "../../../types/project";

interface PromptItem {
  id_or_key: string;
  name: string;
  origin: "official" | "user";
  description?: string | null;
}

interface Props {
  narrationType: NarrationType | undefined;
  featureKey: string;
  /** 与 featureKey 对应的官方默认模板说明（来自接口） */
  defaultOfficialDescription?: string | null;
  selectedIdOrKey: string;
  items: PromptItem[];
  otherOfficialItems: PromptItem[];
  onSelect: (origin: "official" | "user", id_or_key: string) => void;
  onPreview: (id_or_key: string) => void;
  onEditUserTemplate: (id_or_key: string) => void;
  onDeleteUserTemplate: (id: string, name: string) => void;
  onCreateTemplate: () => void;
}

const PromptTemplateList: React.FC<Props> = ({
  narrationType,
  featureKey,
  defaultOfficialDescription,
  selectedIdOrKey,
  items,
  otherOfficialItems,
  onSelect,
  onPreview,
  onEditUserTemplate,
  onDeleteUserTemplate,
  onCreateTemplate,
}) => {
  return (
    <div className="border-gray-200">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-gray-700 mb-2">{`解说风格（${narrationType || NarrationType.SHORT_DRAMA}）`}</label>
      </div>
      <div
        className="max-h-[min(70vh,520px)] overflow-y-auto overflow-x-hidden pr-1 scroll-smooth [scrollbar-gutter:stable] rounded-lg border border-gray-100 bg-gray-50/40"
        role="region"
        aria-label="解说风格模板列表"
      >
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 p-2">
        <div
          className={`
                relative flex flex-col p-3 rounded-lg border cursor-pointer transition-all duration-200 min-h-[80px]
                ${
                  selectedIdOrKey === featureKey
                    ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                    : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                }
             `}
          onClick={() => onSelect("official", featureKey)}
        >
          <div className="flex items-center justify-between mb-1 gap-2">
            <span
              className={`text-sm font-medium shrink min-w-0 ${selectedIdOrKey === featureKey ? "text-violet-900" : "text-gray-900"}`}
            >
              默认风格
            </span>
            {selectedIdOrKey === featureKey && (
              <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center shrink-0">
                <Check className="h-3 w-3 text-white" />
              </div>
            )}
          </div>
          {defaultOfficialDescription ? (
            <p
              className="text-xs text-gray-500 leading-snug line-clamp-4 mb-2"
              title={defaultOfficialDescription}
            >
              {defaultOfficialDescription}
            </p>
          ) : null}
          <div className="mt-auto flex justify-end">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onPreview(featureKey);
              }}
              className="text-xs text-blue-600 hover:underline"
            >
              预览
            </button>
          </div>
        </div>

        {otherOfficialItems.map((it) => {
          const isSelected = selectedIdOrKey === it.id_or_key;
          return (
            <div
              key={it.id_or_key}
              className={`
                  relative flex flex-col p-3 rounded-lg border cursor-pointer transition-all duration-200 min-h-[80px]
                  ${
                    isSelected
                      ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                      : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                  }
                `}
              onClick={() => onSelect("official", it.id_or_key)}
            >
              <div className="flex items-center justify-between mb-1 gap-2">
                <span
                  className={`text-sm font-medium truncate min-w-0 ${isSelected ? "text-violet-900" : "text-gray-900"}`}
                  title={it.name}
                >
                  {it.name}
                </span>
                {isSelected && (
                  <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center shrink-0">
                    <Check className="h-3 w-3 text-white" />
                  </div>
                )}
              </div>
              {it.description ? (
                <p className="text-xs text-gray-500 leading-snug line-clamp-4 mb-2" title={it.description}>
                  {it.description}
                </p>
              ) : null}
              <div className="mt-auto flex justify-end">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onPreview(it.id_or_key);
                  }}
                  className="text-xs text-blue-600 hover:underline"
                >
                  预览
                </button>
              </div>
            </div>
          );
        })}

        {items
          .filter((it) => it.origin === "user")
          .map((it) => {
            const isSelected = selectedIdOrKey === it.id_or_key;
            return (
              <div
                key={it.id_or_key}
                className={`
                  relative flex flex-col p-3 rounded-lg border cursor-pointer transition-all duration-200 min-h-[80px]
                  ${
                    isSelected
                      ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                      : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
                  }
                `}
                onClick={() => onSelect("user", it.id_or_key)}
              >
                <div className="flex items-center justify-between mb-1 gap-2">
                  <div className="flex items-center space-x-2 overflow-hidden min-w-0">
                    <span className="text-[10px] px-1.5 py-0.5 bg-yellow-50 text-yellow-600 rounded border border-yellow-200 whitespace-nowrap shrink-0">
                      自定义
                    </span>
                    <span
                      className={`text-sm font-medium truncate ${isSelected ? "text-violet-900" : "text-gray-900"}`}
                      title={it.name}
                    >
                      {it.name}
                    </span>
                  </div>
                  {isSelected && (
                    <div className="h-4 w-4 rounded-full bg-violet-600 flex items-center justify-center shrink-0 ml-2">
                      <Check className="h-3 w-3 text-white" />
                    </div>
                  )}
                </div>
                {it.description ? (
                  <p className="text-xs text-gray-500 leading-snug line-clamp-3 mb-2 pl-0" title={it.description}>
                    {it.description}
                  </p>
                ) : null}
                <div className="mt-auto flex justify-end space-x-3" onClick={(e) => e.stopPropagation()}>
                  <button onClick={() => onPreview(it.id_or_key)} className="text-xs text-blue-600 hover:underline">
                    预览
                  </button>
                  <button
                    onClick={() => onEditUserTemplate(it.id_or_key)}
                    className="text-xs text-gray-600 hover:underline hover:text-gray-900"
                  >
                    编辑
                  </button>
                  <button
                    onClick={() => onDeleteUserTemplate(it.id_or_key, it.name)}
                    className="h-6 w-6 flex items-center justify-center rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                    title="删除"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        <button
          type="button"
          onClick={onCreateTemplate}
          className="relative flex flex-col items-center justify-center p-3 rounded-lg border border-dashed border-violet-300 text-violet-600 bg-white hover:border-violet-500 hover:bg-violet-50 transition-all duration-200 min-h-[80px]"
        >
          <span className="text-sm font-medium">新建自定义模板</span>
        </button>
        </div>
      </div>
    </div>
  );
};

export default PromptTemplateList;
