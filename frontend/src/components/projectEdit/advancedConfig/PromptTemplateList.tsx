import {
  AudioWaveform,
  Check,
  ChevronRight,
  Crown,
  FileText,
  Film,
  Globe2,
  Megaphone,
  MessageCircle,
  Mic,
  Pencil,
  Plus,
  Shield,
  Sparkles,
  Star,
  Swords,
  Target,
  Trash2,
  UserRound,
  Zap,
  type LucideIcon,
} from "lucide-react";
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
  /** 当前 featureKey 对应的官方默认模板说明（来自接口） */
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

const OFFICIAL_ICONS: LucideIcon[] = [
  Mic,
  UserRound,
  Star,
  MessageCircle,
  Globe2,
  Target,
  Megaphone,
  AudioWaveform,
  Crown,
  Swords,
  Sparkles,
  Film,
  Zap,
  Shield,
];

const FALLBACK_DESCRIPTION = "通用的百科认知类文案生成选项，适用各类主题且易于平台审核和推荐";

const getOfficialIcon = (index: number) => OFFICIAL_ICONS[index % OFFICIAL_ICONS.length];

const TemplateIcon: React.FC<{ icon: LucideIcon; selected?: boolean; user?: boolean }> = ({
  icon: Icon,
  selected = false,
  user = false,
}) => (
  <div
    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-all duration-200 ${
      selected
        ? "border-violet-400/55 bg-violet-500/20 text-violet-200 shadow-[0_0_22px_rgba(124,88,255,0.45)]"
        : user
          ? "border-cyan-300/25 bg-cyan-400/10 text-cyan-200"
          : "border-violet-300/15 bg-violet-500/10 text-violet-300"
    }`}
  >
    <Icon className="h-5 w-5" />
  </div>
);

const PreviewButton: React.FC<{ onClick: (e: React.MouseEvent<HTMLButtonElement>) => void }> = ({ onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="inline-flex items-center gap-0.5 rounded px-1 text-[13px] font-medium text-[#7282ff] transition-colors hover:text-violet-200 focus:outline-none focus:ring-2 focus:ring-violet-400/50"
  >
    预览
    <ChevronRight className="h-3.5 w-3.5" />
  </button>
);

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
  const userItems = items.filter((it) => it.origin === "user");

  const renderTemplateCard = (it: PromptItem, index: number, origin: "official" | "user") => {
    const isSelected = selectedIdOrKey === it.id_or_key;
    const Icon = origin === "user" ? FileText : getOfficialIcon(index);

    return (
      <div
        key={`${origin}-${it.id_or_key}`}
        className={`group relative flex min-h-[104px] cursor-pointer overflow-hidden rounded-lg border p-3.5 transition-all duration-200 ${
          isSelected
            ? "border-violet-400/90 bg-[#151b3f] shadow-[0_0_0_1px_rgba(124,88,255,0.65),0_0_30px_rgba(124,88,255,0.28),inset_0_0_28px_rgba(124,88,255,0.12)]"
            : "border-[#263957] bg-[#0b172b] shadow-[inset_0_1px_0_rgba(255,255,255,0.035)] hover:border-violet-400/45 hover:bg-[#111d36]"
        }`}
        onClick={() => onSelect(origin, it.id_or_key)}
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-violet-300/25 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
        <TemplateIcon icon={Icon} selected={isSelected} user={origin === "user"} />

        <div className="ml-3.5 flex min-w-0 flex-1 flex-col">
          <div className="flex min-w-0 items-start justify-between gap-3">
            <div className="min-w-0">
              {origin === "user" ? (
                <span className="mb-1.5 inline-flex w-fit items-center rounded border border-cyan-300/20 bg-cyan-400/10 px-1.5 py-0.5 text-[10px] font-medium text-cyan-200">
                  自定义
                </span>
              ) : null}
              <h3 className="truncate text-[14px] font-semibold leading-5 text-slate-50" title={it.name}>
                {it.name}
              </h3>
            </div>
            {isSelected ? (
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-500 text-white shadow-[0_0_18px_rgba(124,88,255,0.55)]">
                <Check className="h-4 w-4" />
              </span>
            ) : null}
          </div>

          {it.description ? (
            <p className="mt-1.5 line-clamp-2 text-[12px] leading-[18px] text-[#9eacc9]" title={it.description}>
              {it.description}
            </p>
          ) : (
            <p className="mt-1.5 line-clamp-2 text-[12px] leading-[18px] text-[#667696]">暂无模板说明</p>
          )}

          <div className="mt-auto flex items-center justify-end gap-2 pt-2" onClick={(e) => e.stopPropagation()}>
            <PreviewButton onClick={() => onPreview(it.id_or_key)} />
            {origin === "user" ? (
              <>
                <button
                  type="button"
                  onClick={() => onEditUserTemplate(it.id_or_key)}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md text-[#8a98ba] transition-colors hover:bg-white/10 hover:text-slate-100 focus:outline-none focus:ring-2 focus:ring-violet-400/50"
                  title="编辑"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onDeleteUserTemplate(it.id_or_key, it.name)}
                  className="inline-flex h-7 w-7 items-center justify-center rounded-md text-[#8a98ba] transition-colors hover:bg-red-500/10 hover:text-red-200 focus:outline-none focus:ring-2 focus:ring-red-400/40"
                  title="删除"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </>
            ) : null}
          </div>
        </div>
      </div>
    );
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-semibold text-slate-100">
          解说风格
          <span className="ml-1 text-xs font-medium text-[#8c99b6]">
            （{narrationType || NarrationType.SHORT_DRAMA}）
          </span>
        </label>
      </div>

      <div
        className="max-h-[min(60vh,400px)] overflow-y-auto overflow-x-hidden rounded-lg border border-[#1f3353] bg-[#071326] p-3 scroll-smooth shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_18px_48px_rgba(0,0,0,0.32)] [scrollbar-gutter:stable]"
        role="region"
        aria-label="解说风格模板列表"
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {renderTemplateCard(
            {
              id_or_key: featureKey,
              name: "默认风格",
              origin: "official",
              description: defaultOfficialDescription || FALLBACK_DESCRIPTION,
            },
            11,
            "official"
          )}

          {otherOfficialItems.map((it, index) => renderTemplateCard(it, index, "official"))}
          {userItems.map((it, index) => renderTemplateCard(it, index, "user"))}

          <button
            type="button"
            onClick={onCreateTemplate}
            className="group relative flex min-h-[104px] items-center justify-center overflow-hidden rounded-lg border border-dashed border-violet-300/45 bg-[#0b172b] p-3.5 text-violet-200 transition-all duration-200 hover:border-violet-300 hover:bg-[#151b3f] hover:shadow-[0_0_24px_rgba(124,88,255,0.22)] focus:outline-none focus:ring-2 focus:ring-violet-400/50"
          >
            <span className="absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-violet-300/60 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />
            <span className="flex items-center gap-2 text-sm font-semibold">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-violet-500/18 text-violet-200 shadow-[0_0_18px_rgba(124,88,255,0.28)]">
                <Plus className="h-5 w-5" />
              </span>
              新建自定义模板
            </span>
          </button>
        </div>
      </div>
    </section>
  );
};

export default PromptTemplateList;
