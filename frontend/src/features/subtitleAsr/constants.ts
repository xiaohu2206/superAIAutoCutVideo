export type FunAsrModelOption = {
  id: string;
  label: string;
  keys: string[];
  description?: string;
  recommendedLanguages: string[];
};

export const FUN_ASR_MODEL_OPTIONS: FunAsrModelOption[] = [
  {
    id: "nano_2512",
    label: "Fun-ASR-Nano-2512",
    keys: ["fun_asr_nano_2512", "fsmn_vad"],
    description: "中文/英文/日文（中文含多方言/口音）；推荐多数中文场景。",
    recommendedLanguages: ["中文", "英文", "日文"],
  },
  {
    id: "mlt_nano_2512",
    label: "Fun-ASR-MLT-Nano-2512",
    keys: ["fun_asr_mlt_nano_2512", "fsmn_vad"],
    description: "31 种语言多语种识别；适合外语/混语场景。",
    recommendedLanguages: [
      "中文",
      "英文",
      "粤语",
      "日文",
      "韩文",
      "越南语",
      "印尼语",
      "泰语",
      "马来语",
      "菲律宾语",
      "阿拉伯语",
      "印地语",
      "保加利亚语",
      "克罗地亚语",
      "捷克语",
      "丹麦语",
      "荷兰语",
      "爱沙尼亚语",
      "芬兰语",
      "希腊语",
      "匈牙利语",
      "爱尔兰语",
      "拉脱维亚语",
      "立陶宛语",
      "马耳他语",
      "波兰语",
      "葡萄牙语",
      "罗马尼亚语",
      "斯洛伐克语",
      "斯洛文尼亚语",
      "瑞典语",
    ],
  },
];

export const FUN_ASR_NANO_LANGUAGES = ["中文", "英文", "日文"];

export const FUN_ASR_MLT_LANGUAGES = FUN_ASR_MODEL_OPTIONS.find((x) => x.id === "mlt_nano_2512")?.recommendedLanguages || [];

