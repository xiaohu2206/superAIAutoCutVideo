import type { LucideIcon } from "lucide-react";
import {
  Clapperboard,
  Film,
  Mic,
  Mountain,
  Music2,
  Palette,
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
  cardClassName: string;
  glowClassName: string;
  iconClassName: string;
  actionClassName: string;
}

const NARRATION_TYPE_CARDS: NarrationTypeCard[] = [
  {
    type: NarrationType.MOVIE,
    title: "电影解说",
    description: "院线电影、长片剧情梳理",
    Icon: Film,
    cardClassName: "border-blue-400/30 hover:border-blue-300/70 hover:shadow-[0_0_28px_rgba(37,99,235,0.24)]",
    glowClassName: "bg-blue-500/10",
    iconClassName: "border-blue-400/40 bg-blue-500/15 text-blue-400 shadow-[0_0_24px_rgba(37,99,235,0.34),inset_0_0_18px_rgba(37,99,235,0.18)]",
    actionClassName: "border-blue-400/50 text-blue-200 shadow-[0_0_18px_rgba(37,99,235,0.34),inset_0_0_12px_rgba(37,99,235,0.14)] group-hover:border-blue-300 group-hover:text-white group-hover:shadow-[0_0_24px_rgba(37,99,235,0.48)]",
  },
  {
    type: NarrationType.TV_DRAMA,
    title: "电视剧解说",
    description: "剧集人物关系与单集剧情",
    Icon: Tv2,
    cardClassName: "border-violet-400/25 hover:border-violet-300/65 hover:shadow-[0_0_28px_rgba(124,58,237,0.24)]",
    glowClassName: "bg-violet-500/10",
    iconClassName: "border-violet-400/35 bg-violet-500/15 text-violet-400 shadow-[0_0_24px_rgba(124,58,237,0.34),inset_0_0_18px_rgba(124,58,237,0.18)]",
    actionClassName: "border-violet-400/45 text-violet-200 shadow-[0_0_18px_rgba(124,58,237,0.34),inset_0_0_12px_rgba(124,58,237,0.14)] group-hover:border-violet-300 group-hover:text-white group-hover:shadow-[0_0_24px_rgba(124,58,237,0.48)]",
  },
  {
    type: NarrationType.SHORT_DRAMA,
    title: "短剧解说",
    description: "竖屏短剧、微剧情高节奏拆解",
    Icon: Clapperboard,
    cardClassName: "border-rose-400/25 hover:border-rose-300/65 hover:shadow-[0_0_28px_rgba(244,63,94,0.24)]",
    glowClassName: "bg-rose-500/10",
    iconClassName: "border-rose-400/35 bg-rose-500/15 text-rose-400 shadow-[0_0_24px_rgba(244,63,94,0.34),inset_0_0_18px_rgba(244,63,94,0.18)]",
    actionClassName: "border-rose-400/45 text-rose-200 shadow-[0_0_18px_rgba(244,63,94,0.34),inset_0_0_12px_rgba(244,63,94,0.14)] group-hover:border-rose-300 group-hover:text-white group-hover:shadow-[0_0_24px_rgba(244,63,94,0.48)]",
  },
  {
    type: NarrationType.ANIME,
    title: "动漫解说",
    description: "番剧、动画电影和热血名场面",
    Icon: Palette,
    cardClassName: "border-fuchsia-400/25 hover:border-fuchsia-300/65 hover:shadow-[0_0_28px_rgba(217,70,239,0.24)]",
    glowClassName: "bg-fuchsia-500/10",
    iconClassName: "border-fuchsia-400/35 bg-fuchsia-500/15 text-fuchsia-400 shadow-[0_0_24px_rgba(217,70,239,0.34),inset_0_0_18px_rgba(217,70,239,0.18)]",
    actionClassName: "border-fuchsia-400/45 text-fuchsia-200 shadow-[0_0_18px_rgba(217,70,239,0.34),inset_0_0_12px_rgba(217,70,239,0.14)] group-hover:border-fuchsia-300 group-hover:text-white group-hover:shadow-[0_0_24px_rgba(217,70,239,0.48)]",
  },
  {
    type: NarrationType.VARIETY,
    title: "综艺解说",
    description: "真人秀、热点片段和看点提炼",
    Icon: Music2,
    cardClassName: "border-orange-400/25 hover:border-orange-300/65 hover:shadow-[0_0_28px_rgba(249,115,22,0.24)]",
    glowClassName: "bg-orange-500/10",
    iconClassName: "border-orange-400/35 bg-orange-500/15 text-orange-400 shadow-[0_0_24px_rgba(249,115,22,0.34),inset_0_0_18px_rgba(249,115,22,0.18)]",
    actionClassName: "border-orange-400/45 text-orange-200 shadow-[0_0_18px_rgba(249,115,22,0.34),inset_0_0_12px_rgba(249,115,22,0.14)] group-hover:border-orange-300 group-hover:text-white group-hover:shadow-[0_0_24px_rgba(249,115,22,0.48)]",
  },
  {
    type: NarrationType.DOCUMENTARY,
    title: "纪录片解说",
    description: "自然、人文和纪实影像叙事",
    Icon: Mountain,
    cardClassName: "border-emerald-400/25 hover:border-emerald-300/65 hover:shadow-[0_0_28px_rgba(16,185,129,0.22)]",
    glowClassName: "bg-emerald-500/10",
    iconClassName: "border-emerald-400/35 bg-emerald-500/15 text-emerald-400 shadow-[0_0_24px_rgba(16,185,129,0.30),inset_0_0_18px_rgba(16,185,129,0.18)]",
    actionClassName: "border-emerald-400/45 text-emerald-200 shadow-[0_0_18px_rgba(16,185,129,0.30),inset_0_0_12px_rgba(16,185,129,0.14)] group-hover:border-emerald-300 group-hover:text-white group-hover:shadow-[0_0_24px_rgba(16,185,129,0.44)]",
  },
  {
    type: NarrationType.SPORTS,
    title: "体育解说",
    description: "赛事集锦、关键瞬间复盘",
    Icon: Trophy,
    cardClassName: "border-amber-400/25 hover:border-amber-300/65 hover:shadow-[0_0_28px_rgba(245,158,11,0.24)]",
    glowClassName: "bg-amber-500/10",
    iconClassName: "border-amber-400/35 bg-amber-500/15 text-amber-400 shadow-[0_0_24px_rgba(245,158,11,0.34),inset_0_0_18px_rgba(245,158,11,0.18)]",
    actionClassName: "border-amber-400/45 text-amber-200 shadow-[0_0_18px_rgba(245,158,11,0.34),inset_0_0_12px_rgba(245,158,11,0.14)] group-hover:border-amber-300 group-hover:text-white group-hover:shadow-[0_0_24px_rgba(245,158,11,0.48)]",
  },
  {
    type: NarrationType.GENERAL,
    title: "通用解说",
    description: "适用于多数视频的通用模式",
    Icon: Mic,
    cardClassName: "border-sky-400/25 hover:border-sky-300/65 hover:shadow-[0_0_28px_rgba(14,165,233,0.24)]",
    glowClassName: "bg-sky-500/10",
    iconClassName: "border-sky-400/35 bg-sky-500/15 text-sky-400 shadow-[0_0_24px_rgba(14,165,233,0.34),inset_0_0_18px_rgba(14,165,233,0.18)]",
    actionClassName: "border-sky-400/45 text-sky-200 shadow-[0_0_18px_rgba(14,165,233,0.34),inset_0_0_12px_rgba(14,165,233,0.14)] group-hover:border-sky-300 group-hover:text-white group-hover:shadow-[0_0_24px_rgba(14,165,233,0.48)]",
  },
];

const NarrationTypePicker: React.FC<NarrationTypePickerProps> = ({
  onSelect,
}) => {
  return (
    <section className="relative shrink-0 overflow-hidden rounded-[22px] border border-blue-400/70 bg-[#050b13] px-5 py-5 shadow-[0_0_0_1px_rgba(59,130,246,0.16),0_0_30px_rgba(37,99,235,0.28),inset_0_0_46px_rgba(37,99,235,0.12)] sm:px-8 sm:py-7">
      <div
        className="pointer-events-none absolute left-0 top-0 h-28 w-56 opacity-45 [background-image:radial-gradient(circle,rgba(59,130,246,0.62)_1px,transparent_1px)] [background-size:8px_8px]"
        aria-hidden
      />
      <div
        className="rounded-[22px] pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_10%_0%,rgba(37,99,235,0.20),transparent_28%),radial-gradient(circle_at_100%_100%,rgba(37,99,235,0.10),transparent_32%)]"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute inset-x-8 bottom-0 h-px bg-gradient-to-r from-transparent via-blue-300/80 to-transparent"
        aria-hidden
      />

      <div className="relative mb-6 flex items-center justify-between gap-3 border-b border-blue-300/10 pb-4">
        <div className="flex min-w-0 items-center gap-2">
          <Sparkles className="h-6 w-6 shrink-0 text-blue-400 drop-shadow-[0_0_12px_rgba(59,130,246,0.75)]" aria-hidden />
          <h3 className="truncate text-lg font-semibold text-white drop-shadow-[0_0_12px_rgba(255,255,255,0.28)] sm:text-2xl">
            选择解说类型创建项目
          </h3>
        </div>
      </div>

      <div className="relative grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {NARRATION_TYPE_CARDS.map((card) => {
          const { Icon } = card;
          return (
            <button
              key={card.type}
              type="button"
              onClick={() => onSelect(card.type)}
              className={`group relative flex min-h-[65px] items-center gap-2 overflow-hidden rounded-[10px] border bg-[linear-gradient(145deg,rgba(15,23,42,0.76),rgba(2,6,23,0.90))] px-2.5 py-[9px] text-left transition-all duration-200 hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-blue-300/40 sm:min-h-[72px] sm:px-2.5 sm:py-2.5 ${card.cardClassName}`}
            >
              <span
                className={`pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-200 group-hover:opacity-100 ${card.glowClassName}`}
                aria-hidden
              />
              <div
                className={`relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border sm:h-11 sm:w-11 ${card.iconClassName}`}
              >
                <Icon className="h-[18px] w-[18px] stroke-[1.9] sm:h-[22px] sm:w-[22px]" aria-hidden />
              </div>

              <div className="relative min-w-0 flex-1">
                <div className="truncate text-[13px] font-semibold text-zinc-100 drop-shadow-[0_0_10px_rgba(255,255,255,0.16)] sm:text-sm">
                  {card.title}
                </div>
                <p className="mt-0.5 line-clamp-1 text-[10px] text-slate-400 sm:text-[11px]">
                  {card.description}
                </p>
              </div>

              <div className={`relative flex h-[25px] w-[25px] shrink-0 items-center justify-center rounded-full border bg-[#07111f]/90 transition-all duration-200 sm:h-7 sm:w-7 ${card.actionClassName}`}>
                <Plus className="h-[15px] w-[15px] stroke-[2.2] sm:h-4 sm:w-4" aria-hidden />
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
};

export default NarrationTypePicker;
