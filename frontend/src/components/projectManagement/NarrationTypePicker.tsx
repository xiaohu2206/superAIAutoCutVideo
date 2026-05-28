import type { LucideIcon } from "lucide-react";
import {
  Clapperboard,
  Film,
  Mic,
  Mountain,
  Music2,
  Plus,
  Sparkles,
  Trophy,
  Tv2,
} from "lucide-react";
import React from "react";
import { NarrationType } from "../../types/project";

interface NarrationTypePickerProps {
  onSelect: (narrationType: NarrationType) => void;
}

interface NarrationTypeCard {
  type: NarrationType;
  title: string;
  description: string;
  Icon: LucideIcon;
  accentClassName: string;
  iconClassName: string;
}

const NARRATION_TYPE_CARDS: NarrationTypeCard[] = [
  {
    type: NarrationType.MOVIE,
    title: "电影解说",
    description: "院线电影、长片剧情梳理",
    Icon: Film,
    accentClassName: "hover:border-blue-200 hover:bg-blue-50/30 dark:hover:border-blue-400/30 dark:hover:bg-blue-500/10",
    iconClassName: "bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-300",
  },
  {
    type: NarrationType.TV_DRAMA,
    title: "电视剧解说",
    description: "剧集人物关系与单集剧情",
    Icon: Tv2,
    accentClassName: "hover:border-violet-200 hover:bg-violet-50/30 dark:hover:border-violet-400/30 dark:hover:bg-violet-500/10",
    iconClassName: "bg-violet-50 text-violet-600 dark:bg-violet-500/10 dark:text-violet-300",
  },
  {
    type: NarrationType.SHORT_DRAMA,
    title: "短剧解说",
    description: "竖屏短剧、微剧情高节奏拆解",
    Icon: Clapperboard,
    accentClassName: "hover:border-rose-200 hover:bg-rose-50/30 dark:hover:border-rose-400/30 dark:hover:bg-rose-500/10",
    iconClassName: "bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-300",
  },
  {
    type: NarrationType.VARIETY,
    title: "综艺解说",
    description: "真人秀、热点片段和看点提炼",
    Icon: Music2,
    accentClassName: "hover:border-orange-200 hover:bg-orange-50/30 dark:hover:border-orange-400/30 dark:hover:bg-orange-500/10",
    iconClassName: "bg-orange-50 text-orange-500 dark:bg-orange-500/10 dark:text-orange-300",
  },
  {
    type: NarrationType.DOCUMENTARY,
    title: "纪录片解说",
    description: "自然、人文和纪实影像叙事",
    Icon: Mountain,
    accentClassName: "hover:border-emerald-200 hover:bg-emerald-50/30 dark:hover:border-emerald-400/30 dark:hover:bg-emerald-500/10",
    iconClassName: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-300",
  },
  {
    type: NarrationType.SPORTS,
    title: "体育解说",
    description: "赛事集锦、关键瞬间复盘",
    Icon: Trophy,
    accentClassName: "hover:border-orange-200 hover:bg-orange-50/30 dark:hover:border-orange-400/30 dark:hover:bg-orange-500/10",
    iconClassName: "bg-orange-50 text-orange-500 dark:bg-orange-500/10 dark:text-orange-300",
  },
  {
    type: NarrationType.GENERAL,
    title: "通用解说",
    description: "适用于多数视频的通用模式",
    Icon: Mic,
    accentClassName: "hover:border-sky-200 hover:bg-sky-50/30 dark:hover:border-sky-400/30 dark:hover:bg-sky-500/10",
    iconClassName: "bg-sky-50 text-sky-600 dark:bg-sky-500/10 dark:text-sky-300",
  },
];

const NarrationTypePicker: React.FC<NarrationTypePickerProps> = ({
  onSelect,
}) => {
  return (
    <section className="shrink-0 rounded-lg border border-slate-200 bg-white px-4 py-4 shadow-sm dark:border-white/10 dark:bg-[#1f1f1f] dark:shadow-black/30 sm:px-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Sparkles className="h-4 w-4 shrink-0 text-blue-600 dark:text-blue-300" aria-hidden />
          <h3 className="truncate text-sm font-semibold text-slate-950 dark:text-zinc-100">
            选择解说类型创建项目
          </h3>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {NARRATION_TYPE_CARDS.map((card) => {
          const { Icon } = card;
          return (
            <button
              key={card.type}
              type="button"
              onClick={() => onSelect(card.type)}
              className={`group flex min-h-[66px] items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-3 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-blue-100 dark:border-white/10 dark:bg-[#242424] dark:focus:ring-blue-500/30 ${card.accentClassName}`}
            >
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${card.iconClassName}`}
              >
                <Icon className="h-5 w-5" aria-hidden />
              </div>

              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-slate-950 dark:text-zinc-100">
                  {card.title}
                </div>
                <p className="mt-1 line-clamp-1 text-xs text-slate-500 dark:text-zinc-400">
                  {card.description}
                </p>
              </div>

              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-500 transition-colors group-hover:border-blue-200 group-hover:text-blue-600 dark:border-white/10 dark:bg-[#1f1f1f] dark:text-zinc-400 dark:group-hover:border-blue-400/30 dark:group-hover:text-blue-300">
                <Plus className="h-4 w-4 stroke-[2.4]" aria-hidden />
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
};

export default NarrationTypePicker;
