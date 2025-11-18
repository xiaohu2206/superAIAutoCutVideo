  export const getGenderLabel = (g?: string) => {
    const s = (g || "").toLowerCase();
    if (s === "male") return "男声";
    if (s === "female") return "女声";
    if (s === "boy") return "男童";
    if (s === "girl") return "女童";
    return g || "";
  };