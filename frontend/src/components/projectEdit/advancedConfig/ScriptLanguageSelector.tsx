import React from "react";

interface Props {
  scriptLanguage: "zh" | "en";
  loading: boolean;
  saving: boolean;
  setScriptLanguageAndPersist: (value: "zh" | "en") => Promise<void>;
}

const ScriptLanguageSelector: React.FC<Props> = ({
  scriptLanguage,
  loading,
  saving,
  setScriptLanguageAndPersist,
}) => {
  const options: Array<{ value: "zh" | "en"; title: string; subtitle: string }> = [
    { value: "zh", title: "中文", subtitle: "生成中文解说文本" },
    { value: "en", title: "English", subtitle: "Generate English narration" },
  ];

  return (
    <div className="border-t border-gray-200 pt-4">
      <div className="flex items-center justify-between">
        <label className="block text-sm font-medium text-gray-700 mb-2">脚本语言</label>
        {loading ? (
          <span className="text-xs text-gray-500">加载中</span>
        ) : saving ? (
          <span className="text-xs text-gray-500">保存中</span>
        ) : (
          <span className="text-xs text-gray-500">选择模型输出语言</span>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {options.map((opt) => {
          const isSelected = scriptLanguage === opt.value;
          return (
            <div
              key={opt.value}
              className={`relative flex flex-col justify-between p-3 rounded-lg border cursor-pointer transition-all duration-200 ${
                isSelected
                  ? "border-violet-600 bg-violet-50 ring-1 ring-violet-600 shadow-sm"
                  : "border-gray-200 bg-white hover:border-violet-300 hover:shadow-sm"
              }`}
              onClick={() => void setScriptLanguageAndPersist(opt.value)}
            >
              <div className="flex items-center justify-between mb-1">
                <span className={`text-sm font-medium ${isSelected ? "text-violet-900" : "text-gray-900"}`}>
                  {opt.title}
                </span>
                {isSelected && <div className="h-4 w-4 rounded-full bg-violet-600" />}
              </div>
              <span className={`text-xs ${isSelected ? "text-violet-700" : "text-gray-500"}`}>{opt.subtitle}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default ScriptLanguageSelector;
