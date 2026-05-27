import { NarrationType } from "../types/project";

export interface NarrationTypeOption {
  label: string;
  value: NarrationType;
  promptCategory: string;
}

export const NARRATION_TYPE_OPTIONS: NarrationTypeOption[] = [
  { label: "短剧解说", value: NarrationType.SHORT_DRAMA, promptCategory: "short_drama_narration" },
  { label: "电影解说", value: NarrationType.MOVIE, promptCategory: "movie_narration" },
  { label: "电视剧解说", value: NarrationType.TV_DRAMA, promptCategory: "tv_drama_narration" },
  { label: "综艺解说", value: NarrationType.VARIETY, promptCategory: "variety_narration" },
  { label: "纪录片解说", value: NarrationType.DOCUMENTARY, promptCategory: "documentary_narration" },
  { label: "体育解说", value: NarrationType.SPORTS, promptCategory: "sports_narration" },
  { label: "通用解说", value: NarrationType.GENERAL, promptCategory: "general_narration" },
];

export function getPromptCategoryByNarrationType(narrationType?: NarrationType): string {
  const opt = NARRATION_TYPE_OPTIONS.find((item) => item.value === narrationType);
  return opt?.promptCategory || "short_drama_narration";
}
