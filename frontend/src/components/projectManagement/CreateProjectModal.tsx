// 创建项目模态框组件

import React, { useEffect, useState } from "react";
import { X, Folder } from "lucide-react";
import type { CreateProjectRequest, OmniEffectTier } from "../../types/project";
import { NarrationType } from "../../types/project";
import unifiedYunwuModelService from "../../services/unifiedYunwuModelService";
import videoModelService from "../../services/videoModelService";
import AppSelect from "../ui/AppSelect";
import { useAuth } from "../auth/AuthContext";

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: CreateProjectRequest) => Promise<void>;
  onShowLogin?: () => void;
  onShowProfile?: () => void;
}

/**
 * 创建项目模态框组件
 */
const CreateProjectModal: React.FC<CreateProjectModalProps> = ({
  isOpen,
  onClose,
  onCreate,
  onShowLogin,
  onShowProfile,
}) => {
  const { isAuthenticated } = useAuth();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [narrationType, setNarrationType] = useState<NarrationType>(
    NarrationType.MOVIE
  );
  const [projectType, setProjectType] = useState<"subtitle" | "visual" | "omni">("subtitle");
  const [omniEffectTier, setOmniEffectTier] = useState<OmniEffectTier>("high");
  /** null：尚未拉取；与设置页「使用自定义模型」一致，为 true 时不展示全感知档位 */
  const [yunwuUseCustomModels, setYunwuUseCustomModels] = useState<boolean | null>(null);
  /** 当前启用的视频分析模型是否为 moondream 本地模型 */
  const [isMoondreamEnabled, setIsMoondreamEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showOmniEffectTier =
    projectType === "omni" && yunwuUseCustomModels === false;

  useEffect(() => {
    if (!isOpen) {
      setYunwuUseCustomModels(null);
      setIsMoondreamEnabled(false);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const res = await unifiedYunwuModelService.get();
        const data = res?.data;
        if (cancelled) return;
        if (res?.success && data && typeof data === "object") {
          setYunwuUseCustomModels(Boolean(data.use_custom_models));
        } else {
          setYunwuUseCustomModels(false);
        }
      } catch {
        if (!cancelled) setYunwuUseCustomModels(false);
      }

      try {
        const videoRes = await videoModelService.getConfigs();
        if (cancelled) return;
        if (videoRes?.success && videoRes.data?.configs) {
          const configs = videoRes.data.configs;
          const enabledConfigId = Object.keys(configs).find(
            (id) => configs[id].enabled === true
          );
          const isMoondream =
            enabledConfigId && configs[enabledConfigId].provider === "moondream";
          setIsMoondreamEnabled(!!isMoondream);
        } else {
          setIsMoondreamEnabled(false);
        }
      } catch {
        if (!cancelled) setIsMoondreamEnabled(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  /**
   * 处理提交
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      setError("请输入项目名称");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const payload: CreateProjectRequest = {
        name: name.trim(),
        description: description.trim() || undefined,
        narration_type: narrationType,
        project_type: projectType,
      };
      if (showOmniEffectTier) {
        payload.omni_effect_tier = omniEffectTier;
      }
      await onCreate(payload);

      // 重置表单
      setName("");
      setDescription("");
      setNarrationType(NarrationType.SHORT_DRAMA);
      setProjectType("subtitle");
      setOmniEffectTier("high");
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "创建项目失败";
      if (projectType === "omni") {
        const isLicenseError = /license|401|403|登录|未授权|无权限|过期|校验|绑定/i.test(msg);
        if (isLicenseError) {
          setError(msg);
          onClose();
          if (!isAuthenticated) {
            onShowLogin?.();
          } else {
            onShowProfile?.();
          }
          return;
        }
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  /**
   * 处理关闭
   */
  const handleClose = () => {
    if (!loading) {
      setName("");
      setDescription("");
      setOmniEffectTier("high");
      setError(null);
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* 遮罩层 */}
      <div
        className="fixed inset-0 bg-black bg-opacity-50 transition-opacity"
        onClick={handleClose}
      />

      {/* 模态框内容 */}
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-2xl w-full">
          {/* 头部 */}
          <div className="flex items-center justify-between p-6 border-b border-gray-200">
            <div className="flex items-center space-x-3">
              <div className="flex items-center justify-center w-10 h-10 bg-blue-100 rounded-lg">
                <Folder className="h-5 w-5 text-blue-600" />
              </div>
              <h3 className="text-xl font-semibold text-gray-900">
                创建新项目
              </h3>
            </div>
            <button
              onClick={handleClose}
              disabled={loading}
              className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          {/* 表单内容 */}
          <form onSubmit={handleSubmit} className="p-6 space-y-4">
            {/* 错误提示 */}
            {error && (
              <div className="bg-red-50 text-red-600 px-4 py-3 rounded-lg text-sm">
                {error}
              </div>
            )}

            {/* 项目名称 */}
            <div>
              <label
                htmlFor="project-name"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                项目名称 <span className="text-red-500">*</span>
              </label>
              <input
                id="project-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="必须填影视名称"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                disabled={loading}
                required
              />
            </div>

            {/* 推理模式 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                推理模式 <span className="text-red-500">*</span>
              </label>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* 快速推理 */}
                <div
                  onClick={() => !loading && setProjectType("subtitle")}
                  className={`relative p-4 border-2 rounded-lg cursor-pointer transition-all ${
                    projectType === "subtitle"
                      ? "border-green-500 bg-green-50"
                      : "border-gray-200 bg-white hover:border-green-300"
                  }`}
                >
                  {projectType === "subtitle" && (
                    <div className="absolute top-3 right-3 w-4 h-4 bg-green-500 rounded-full border-2 border-white shadow-sm"></div>
                  )}
                  <h4
                    className={`text-lg font-bold mb-2 ${
                      projectType === "subtitle" ? "text-green-700" : "text-gray-700"
                    }`}
                  >
                    字幕推理
                  </h4>
                  <div className="space-y-1">
                    <p className="text-xs text-gray-500">适用：适用于普通话视频</p>
                  </div>
                </div>

                {/* 深度推理 */}
                <div
                  onClick={() => !loading && setProjectType("visual")}
                  className={`relative p-4 border-2 rounded-lg cursor-pointer transition-all ${
                    projectType === "visual"
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200 bg-white hover:border-blue-300"
                  }`}
                >
                  {projectType === "visual" && (
                    <div className="absolute top-3 right-3 w-4 h-4 bg-blue-500 rounded-full border-2 border-white shadow-sm"></div>
                  )}
                  <div className="flex items-center justify-between mb-2">
                    <h4
                      className={`text-lg font-bold ${
                        projectType === "visual" ? "text-blue-700" : "text-gray-700"
                      }`}
                    >
                      视觉推理
                    </h4>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-gray-500">适用：适用所有类型的视频</p>
                  </div>
                </div>

                {/* 全感知推理 */}
                <div
                  onClick={() => {
                    if (loading) return;
                    if (isMoondreamEnabled) {
                      setError("本地模型不支持全感知推理");
                      return;
                    }
                    setProjectType("omni");
                  }}
                  className={`relative p-4 border-2 rounded-lg transition-all ${
                    isMoondreamEnabled
                      ? "border-gray-200 bg-gray-100 cursor-not-allowed opacity-50"
                      : projectType === "omni"
                        ? "border-purple-500 bg-purple-50 cursor-pointer"
                        : "border-gray-200 bg-white hover:border-purple-300 cursor-pointer"
                  }`}
                >
                  {projectType === "omni" && !isMoondreamEnabled && (
                    <div className="absolute top-3 right-3 w-4 h-4 bg-purple-500 rounded-full border-2 border-white shadow-sm"></div>
                  )}
                  <div className="flex items-center justify-between mb-2">
                    <h4
                      className={`text-lg font-bold ${
                        projectType === "omni" && !isMoondreamEnabled
                          ? "text-purple-700"
                          : "text-gray-700"
                      }`}
                    >
                      全感知推理
                    </h4>
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-gray-500">适用：字幕与视觉信息联合分析的视频</p>
                  </div>
                </div>
              </div>
            </div>

            {showOmniEffectTier && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  全感知生成效果 <span className="text-red-500">*</span>
                </label>
                <p className="text-xs text-gray-500 mb-3">
                  档位越高，模型调用与计算越多，效果通常越好；默认高消耗。
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {(
                    [
                      {
                        tier: "low" as const,
                        title: "低消耗",
                        sub: "低效果",
                        activeBorder: "border-amber-500",
                        activeBg: "bg-amber-50",
                        hoverBorder: "hover:border-amber-300",
                        titleActive: "text-amber-800",
                        dot: "bg-amber-500",
                      },
                      {
                        tier: "medium" as const,
                        title: "中消耗",
                        sub: "均衡",
                        activeBorder: "border-purple-500",
                        activeBg: "bg-purple-50",
                        hoverBorder: "hover:border-purple-300",
                        titleActive: "text-purple-800",
                        dot: "bg-purple-500",
                      },
                      {
                        tier: "high" as const,
                        title: "高消耗",
                        sub: "高效果",
                        activeBorder: "border-violet-600",
                        activeBg: "bg-violet-50",
                        hoverBorder: "hover:border-violet-400",
                        titleActive: "text-violet-900",
                        dot: "bg-violet-600",
                      },
                    ] as const
                  ).map((opt) => (
                    <div
                      key={opt.tier}
                      onClick={() => !loading && setOmniEffectTier(opt.tier)}
                      className={`relative p-3 border-2 rounded-lg cursor-pointer transition-all ${
                        omniEffectTier === opt.tier
                          ? `${opt.activeBorder} ${opt.activeBg}`
                          : `border-gray-200 bg-white ${opt.hoverBorder}`
                      }`}
                    >
                      {omniEffectTier === opt.tier && (
                        <div
                          className={`absolute top-2 right-2 w-3.5 h-3.5 ${opt.dot} rounded-full border-2 border-white shadow-sm`}
                        />
                      )}
                      <h4
                        className={`text-sm font-bold ${
                          omniEffectTier === opt.tier ? opt.titleActive : "text-gray-700"
                        }`}
                      >
                        {opt.title}
                      </h4>
                      <p className="text-xs text-gray-500 mt-0.5">{opt.sub}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 项目描述 */}
            {/* <div>
              <label
                htmlFor="project-description"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                项目描述
              </label>
              <textarea
                id="project-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="请输入项目描述（可选）"
                rows={2}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none"
                disabled={loading}
              />
            </div> */}

            {/* 解说类型 */}
            <div>
              <label
                htmlFor="narration-type"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                解说类型
              </label>
              <AppSelect
                id="narration-type"
                value={narrationType}
                onChange={(e) =>
                  setNarrationType(e.target.value as NarrationType)
                }
                disabled={loading}
              >
                <option value={NarrationType.SHORT_DRAMA}>短剧解说</option>
                <option value={NarrationType.MOVIE}>电影解说</option>
              </AppSelect>
            </div>

            {/* 按钮组 */}
            <div className="flex items-center justify-end space-x-3 pt-4">
              <button
                type="button"
                onClick={handleClose}
                disabled={loading}
                className="px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition-colors disabled:opacity-50"
              >
                取消
              </button>
              <button
                type="submit"
                disabled={loading || !name.trim()}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? "创建中..." : "创建项目"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default CreateProjectModal;
