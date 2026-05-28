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
import { useThemeMode } from "../../../hooks/useThemeMode";
import { NarrationType } from "../../../types/project";

interface PromptItem {
  id_or_key: string;
  name: string;
  origin: "official" | "user";
  description?: string | null;
}

export type PromptTemplateListVariant = "dark" | "light";

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
  /** 视觉风格，默认深色，亮色用于浅底容器 */
  variant?: PromptTemplateListVariant;
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

interface ThemeTokens {
  sectionLabel: string;
  sectionLabelSub: string;
  scrollContainer: string;
  card: {
    base: string;
    selected: string;
    unselected: string;
    topHair: string;
  };
  icon: {
    selected: string;
    user: string;
    official: string;
  };
  customBadge: string;
  title: string;
  description: string;
  descriptionEmpty: string;
  selectedCheck: string;
  previewBtn: string;
  iconBtn: string;
  iconBtnDanger: string;
  createBtn: string;
  createBtnHair: string;
  createIcon: string;
}

/** 深海军蓝面板（Omni 等工作区） */
const THEME_NAVY: ThemeTokens = {
    sectionLabel: "text-slate-100",
    sectionLabelSub: "text-[#8c99b6]",
    scrollContainer:
      "rounded-lg border border-[#1f3353] bg-[#071326] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04),0_18px_48px_rgba(0,0,0,0.32)]",
    card: {
      base: "border p-3.5 transition-all duration-200",
      selected:
        "border-violet-400/90 bg-[#151b3f] shadow-[0_0_0_1px_rgba(124,88,255,0.65),0_0_30px_rgba(124,88,255,0.28),inset_0_0_28px_rgba(124,88,255,0.12)]",
      unselected:
        "border-[#263957] bg-[#0b172b] shadow-[inset_0_1px_0_rgba(255,255,255,0.035)] hover:border-violet-400/45 hover:bg-[#111d36]",
      topHair:
        "bg-gradient-to-r from-transparent via-violet-300/25 to-transparent",
    },
    icon: {
      selected:
        "border-violet-400/55 bg-violet-500/20 text-violet-200 shadow-[0_0_22px_rgba(124,88,255,0.45)]",
      user: "border-cyan-300/25 bg-cyan-400/10 text-cyan-200",
      official: "border-violet-300/15 bg-violet-500/10 text-violet-300",
    },
    customBadge:
      "border border-cyan-300/20 bg-cyan-400/10 text-cyan-200",
    title: "text-slate-50",
    description: "text-[#9eacc9]",
    descriptionEmpty: "text-[#667696]",
    selectedCheck:
      "bg-violet-500 text-white shadow-[0_0_18px_rgba(124,88,255,0.55)]",
    previewBtn:
      "text-[#7282ff] hover:text-violet-200 focus:ring-violet-400/50",
    iconBtn:
      "text-[#8a98ba] hover:bg-white/10 hover:text-slate-100 focus:ring-violet-400/50",
    iconBtnDanger:
      "text-[#8a98ba] hover:bg-red-500/10 hover:text-red-200 focus:ring-red-400/40",
    createBtn:
      "border-dashed border-violet-300/45 bg-[#0b172b] text-violet-200 hover:border-violet-300 hover:bg-[#151b3f] hover:shadow-[0_0_24px_rgba(124,88,255,0.22)] focus:ring-violet-400/50",
    createBtnHair:
      "bg-gradient-to-r from-transparent via-violet-300/60 to-transparent",
    createIcon:
      "bg-violet-500/18 text-violet-200 shadow-[0_0_18px_rgba(124,88,255,0.28)]",
};

/** 标准卡片页 — 亮色模式（父容器 bg-white） */
const THEME_PANEL_LIGHT: ThemeTokens = {
  sectionLabel: "text-gray-700",
  sectionLabelSub: "text-gray-400",
  scrollContainer:
    "rounded-lg border border-gray-200 bg-gray-50/60 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.6),0_1px_2px_rgba(15,23,42,0.04)]",
  card: {
    base: "border p-3.5 transition-all duration-200",
    selected: "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm",
    unselected: "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm",
    topHair: "bg-gradient-to-r from-transparent via-violet-400/40 to-transparent",
  },
  icon: {
    selected: "border-violet-300 bg-violet-100 text-violet-700",
    user: "border-cyan-200 bg-cyan-50 text-cyan-600",
    official: "border-violet-100 bg-violet-50 text-violet-600",
  },
  customBadge: "border border-cyan-200 bg-cyan-50 text-cyan-700",
  title: "text-gray-900",
  description: "text-gray-600",
  descriptionEmpty: "text-gray-400",
  selectedCheck: "bg-violet-600 text-white shadow-sm",
  previewBtn: "text-violet-600 hover:text-violet-700 focus:ring-violet-400/40",
  iconBtn: "text-gray-400 hover:bg-gray-100 hover:text-gray-700 focus:ring-violet-400/40",
  iconBtnDanger: "text-gray-400 hover:bg-red-50 hover:text-red-600 focus:ring-red-400/40",
  createBtn:
    "border-dashed border-violet-300 bg-white text-violet-600 hover:border-violet-400 hover:bg-violet-50 hover:shadow-sm focus:ring-violet-400/40",
  createBtnHair: "bg-gradient-to-r from-transparent via-violet-400/40 to-transparent",
  createIcon: "bg-violet-100 text-violet-600",
};

/** 标准卡片页 — 暗色模式（父容器 dark:bg-[#1f1f1f]，与 ScriptLanguageSelector 一致） */
const THEME_PANEL_DARK: ThemeTokens = {
  sectionLabel: "text-zinc-200",
  sectionLabelSub: "text-zinc-500",
  scrollContainer: "rounded-lg border border-[#2a2a2a] bg-[#181818] p-3 shadow-black/30",
  card: {
    base: "border p-3.5 transition-all duration-200",
    selected:
      "border-violet-500 bg-violet-900/20 ring-1 ring-violet-500 shadow-[0_0_0_1px_rgba(139,92,246,0.35),0_0_18px_rgba(139,92,246,0.12)]",
    unselected:
      "border-[#2a2a2a] bg-[#242424] hover:border-violet-500/50 hover:bg-[#2a2a2a]",
    topHair: "bg-gradient-to-r from-transparent via-violet-400/30 to-transparent",
  },
  icon: {
    selected: "border-violet-400/50 bg-violet-500/20 text-violet-200",
    user: "border-cyan-400/30 bg-cyan-500/10 text-cyan-300",
    official: "border-violet-400/20 bg-violet-500/10 text-violet-300",
  },
  customBadge: "border border-cyan-400/30 bg-cyan-500/10 text-cyan-300",
  title: "text-zinc-100",
  description: "text-zinc-400",
  descriptionEmpty: "text-zinc-500",
  selectedCheck: "bg-violet-500 text-white shadow-[0_0_14px_rgba(139,92,246,0.45)]",
  previewBtn: "text-violet-300 hover:text-violet-200 focus:ring-violet-400/40",
  iconBtn: "text-zinc-500 hover:bg-white/5 hover:text-zinc-200 focus:ring-violet-400/40",
  iconBtnDanger: "text-zinc-500 hover:bg-red-500/10 hover:text-red-300 focus:ring-red-400/40",
  createBtn:
    "border-dashed border-violet-400/40 bg-[#242424] text-violet-300 hover:border-violet-300/60 hover:bg-[#2a2a2a] focus:ring-violet-400/40",
  createBtnHair: "bg-gradient-to-r from-transparent via-violet-300/40 to-transparent",
  createIcon: "bg-violet-500/15 text-violet-200",
};

const resolveTheme = (variant: PromptTemplateListVariant, colorMode: "light" | "dark"): ThemeTokens => {
  if (variant === "dark") return THEME_NAVY;
  return colorMode === "dark" ? THEME_PANEL_DARK : THEME_PANEL_LIGHT;
};

const TemplateIcon: React.FC<{
  icon: LucideIcon;
  selected?: boolean;
  user?: boolean;
  theme: ThemeTokens;
}> = ({ icon: Icon, selected = false, user = false, theme }) => (
  <div
    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-all duration-200 ${
      selected ? theme.icon.selected : user ? theme.icon.user : theme.icon.official
    }`}
  >
    <Icon className="h-5 w-5" />
  </div>
);

const PreviewButton: React.FC<{
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
  theme: ThemeTokens;
}> = ({ onClick, theme }) => (
  <button
    type="button"
    onClick={onClick}
    className={`inline-flex items-center gap-0.5 rounded px-1 text-[13px] font-medium transition-colors focus:outline-none focus:ring-2 ${theme.previewBtn}`}
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
  variant = "dark",
}) => {
  const colorMode = useThemeMode();
  const theme = resolveTheme(variant, colorMode);
  const userItems = items.filter((it) => it.origin === "user");

  const renderTemplateCard = (it: PromptItem, index: number, origin: "official" | "user") => {
    const isSelected = selectedIdOrKey === it.id_or_key;
    const Icon = origin === "user" ? FileText : getOfficialIcon(index);

    return (
      <div
        key={`${origin}-${it.id_or_key}`}
        className={`group relative flex min-h-[104px] cursor-pointer overflow-hidden rounded-lg ${theme.card.base} ${
          isSelected ? theme.card.selected : theme.card.unselected
        }`}
        onClick={() => onSelect(origin, it.id_or_key)}
      >
        <div
          className={`pointer-events-none absolute inset-x-0 top-0 h-px opacity-0 transition-opacity group-hover:opacity-100 ${theme.card.topHair}`}
        />
        <TemplateIcon icon={Icon} selected={isSelected} user={origin === "user"} theme={theme} />

        <div className="ml-3.5 flex min-w-0 flex-1 flex-col">
          <div className="flex min-w-0 items-start justify-between gap-3">
            <div className="min-w-0">
              {origin === "user" ? (
                <span
                  className={`mb-1.5 inline-flex w-fit items-center rounded px-1.5 py-0.5 text-[10px] font-medium ${theme.customBadge}`}
                >
                  自定义
                </span>
              ) : null}
              <h3 className={`truncate text-[14px] font-semibold leading-5 ${theme.title}`} title={it.name}>
                {it.name}
              </h3>
            </div>
            {isSelected ? (
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${theme.selectedCheck}`}
              >
                <Check className="h-4 w-4" />
              </span>
            ) : null}
          </div>

          {it.description ? (
            <p
              className={`mt-1.5 line-clamp-2 text-[12px] leading-[18px] ${theme.description}`}
              title={it.description}
            >
              {it.description}
            </p>
          ) : (
            <p className={`mt-1.5 line-clamp-2 text-[12px] leading-[18px] ${theme.descriptionEmpty}`}>暂无模板说明</p>
          )}

          <div className="mt-auto flex items-center justify-end gap-2 pt-2" onClick={(e) => e.stopPropagation()}>
            <PreviewButton onClick={() => onPreview(it.id_or_key)} theme={theme} />
            {origin === "user" ? (
              <>
                <button
                  type="button"
                  onClick={() => onEditUserTemplate(it.id_or_key)}
                  className={`inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors focus:outline-none focus:ring-2 ${theme.iconBtn}`}
                  title="编辑"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onDeleteUserTemplate(it.id_or_key, it.name)}
                  className={`inline-flex h-7 w-7 items-center justify-center rounded-md transition-colors focus:outline-none focus:ring-2 ${theme.iconBtnDanger}`}
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
        <label className={`block text-sm font-semibold ${theme.sectionLabel}`}>
          解说风格
          <span className={`ml-1 text-xs font-medium ${theme.sectionLabelSub}`}>
            （{narrationType || NarrationType.SHORT_DRAMA}）
          </span>
        </label>
      </div>

      <div
        className={`max-h-[min(60vh,400px)] overflow-y-auto overflow-x-hidden scroll-smooth [scrollbar-gutter:stable] ${theme.scrollContainer}`}
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
            className={`group relative flex min-h-[104px] items-center justify-center overflow-hidden rounded-lg border p-3.5 transition-all duration-200 focus:outline-none focus:ring-2 ${theme.createBtn}`}
          >
            <span
              className={`absolute inset-x-10 top-0 h-px opacity-0 transition-opacity group-hover:opacity-100 ${theme.createBtnHair}`}
            />
            <span className="flex items-center gap-2 text-sm font-semibold">
              <span
                className={`flex h-9 w-9 items-center justify-center rounded-full ${theme.createIcon}`}
              >
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
