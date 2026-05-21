// 解说类型选择器：以卡片网格形式列出全部解说类型，点击即触发创建项目流程

import React from "react";
import {
  Film,
  Mic,
  Mountain,
  Music2,
  Plus,
  Sparkles,
  Trophy,
  Tv2,
  Wand2,
} from "lucide-react";
import { NarrationType } from "../../types/project";

interface NarrationTypePickerProps {
  /** 用户点击某个解说类型卡片时触发，传入对应类型 */
  onSelect: (narrationType: NarrationType) => void;
}

/**
 * 单个解说类型卡片的视觉配置
 * 将「颜色 + 图标 + 描述」集中在这里，便于按需调整不影响主流程
 */
interface NarrationTypeCard {
  type: NarrationType;
  title: string;
  description: string;
  Icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  /** 卡片 hover 边框颜色 */
  hoverBorder: string;
  /** 图标底色与文字色 */
  iconBg: string;
  iconColor: string;
  /** 卡片背景渐变 */
  bgGradient: string;
  /** hover 时的微光圆环 */
  ringHover: string;
}

const NARRATION_TYPE_CARDS: NarrationTypeCard[] = [
  {
    type: NarrationType.SHORT_DRAMA,
    title: "短剧解说",
    description: "节奏紧凑，适合竖屏短剧/微剧",
    Icon: Tv2,
    hoverBorder: "hover:border-rose-300",
    iconBg: "bg-rose-100",
    iconColor: "text-rose-600",
    bgGradient: "from-rose-50/70 via-white to-white",
    ringHover: "hover:ring-rose-200/60",
  },
  {
    type: NarrationType.MOVIE,
    title: "电影解说",
    description: "适合院线电影、长片剧情梳理",
    Icon: Film,
    hoverBorder: "hover:border-blue-300",
    iconBg: "bg-blue-100",
    iconColor: "text-blue-600",
    bgGradient: "from-blue-50/70 via-white to-white",
    ringHover: "hover:ring-blue-200/60",
  },
  {
    type: NarrationType.VARIETY,
    title: "综艺解说",
    description: "明星综艺、真人秀亮点提炼",
    Icon: Music2,
    hoverBorder: "hover:border-amber-300",
    iconBg: "bg-amber-100",
    iconColor: "text-amber-600",
    bgGradient: "from-amber-50/70 via-white to-white",
    ringHover: "hover:ring-amber-200/60",
  },
  {
    type: NarrationType.DOCUMENTARY,
    title: "纪录片解说",
    description: "自然、人文等纪实影像叙述",
    Icon: Mountain,
    hoverBorder: "hover:border-emerald-300",
    iconBg: "bg-emerald-100",
    iconColor: "text-emerald-600",
    bgGradient: "from-emerald-50/70 via-white to-white",
    ringHover: "hover:ring-emerald-200/60",
  },
  {
    type: NarrationType.SPORTS,
    title: "体育解说",
    description: "赛事集锦、激情瞬间复盘",
    Icon: Trophy,
    hoverBorder: "hover:border-orange-300",
    iconBg: "bg-orange-100",
    iconColor: "text-orange-600",
    bgGradient: "from-orange-50/70 via-white to-white",
    ringHover: "hover:ring-orange-200/60",
  },
  {
    type: NarrationType.GENERAL,
    title: "通用解说",
    description: "适用于多数视频的通用模式",
    Icon: Mic,
    hoverBorder: "hover:border-slate-300",
    iconBg: "bg-slate-100",
    iconColor: "text-slate-600",
    bgGradient: "from-slate-50/70 via-white to-white",
    ringHover: "hover:ring-slate-200/60",
  },
  {
    type: NarrationType.CUSTOM,
    title: "自定义解说",
    description: "使用自定义提示词模板创作",
    Icon: Wand2,
    hoverBorder: "hover:border-violet-300",
    iconBg: "bg-violet-100",
    iconColor: "text-violet-600",
    bgGradient: "from-violet-50/70 via-white to-white",
    ringHover: "hover:ring-violet-200/60",
  },
];

/**
 * 解说类型选择器组件
 *
 * 设计要点：
 * - 顶部 hint 行说明该区域作为创建项目的入口
 * - 卡片按 3 列网格排布（小屏自适应为 1/2 列），按解说类型分配色调
 * - 每张卡片右上角带 Plus 提示「点击创建」
 */
const NarrationTypePicker: React.FC<NarrationTypePickerProps> = ({
  onSelect,
}) => {
  return (
    <section className="px-1">
      <div className="mb-3 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-blue-500" aria-hidden />
        <h3 className="text-sm font-semibold text-gray-700">
          选择解说类型创建项目
        </h3>
        <span className="text-xs text-gray-400">点击下方任意类型快速开始</span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {NARRATION_TYPE_CARDS.map((card) => {
          const { Icon } = card;
          return (
            <button
              key={card.type}
              type="button"
              onClick={() => onSelect(card.type)}
              className={`group relative flex items-center gap-3 rounded-xl border border-gray-200 bg-gradient-to-br ${card.bgGradient} px-4 py-3 text-left shadow-sm ring-0 transition-all hover:-translate-y-0.5 hover:shadow-md ${card.hoverBorder} hover:ring-2 ${card.ringHover} focus:outline-none focus:ring-2 focus:ring-blue-300`}
            >
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${card.iconBg} ${card.iconColor}`}
              >
                <Icon className="h-5 w-5" aria-hidden />
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-sm font-semibold text-gray-900">
                    {card.title}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-xs text-gray-500">
                  {card.description}
                </p>
              </div>

              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/90 text-gray-400 shadow-sm ring-1 ring-gray-200 transition-colors group-hover:bg-blue-600 group-hover:text-white group-hover:ring-blue-500">
                <Plus className="h-4 w-4" aria-hidden />
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
};

export default NarrationTypePicker;
