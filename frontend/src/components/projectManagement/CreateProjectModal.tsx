// 创建项目模态框组件

import React, { useState } from "react";
import { X, Folder } from "lucide-react";
import { NarrationType } from "../../types/project";

interface CreateProjectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: {
    name: string;
    description?: string;
    narration_type: NarrationType;
  }) => Promise<void>;
}

/**
 * 创建项目模态框组件
 */
const CreateProjectModal: React.FC<CreateProjectModalProps> = ({
  isOpen,
  onClose,
  onCreate,
}) => {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [narrationType, setNarrationType] = useState<NarrationType>(
    NarrationType.SHORT_DRAMA
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      await onCreate({
        name: name.trim(),
        description: description.trim() || undefined,
        narration_type: narrationType,
      });

      // 重置表单
      setName("");
      setDescription("");
      setNarrationType(NarrationType.SHORT_DRAMA);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建项目失败");
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
        <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full">
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
                placeholder="请输入项目名称"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                disabled={loading}
                required
              />
            </div>

            {/* 项目描述 */}
            <div>
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
                rows={3}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all resize-none"
                disabled={loading}
              />
            </div>

            {/* 解说类型 */}
            <div>
              <label
                htmlFor="narration-type"
                className="block text-sm font-medium text-gray-700 mb-2"
              >
                解说类型
              </label>
              <select
                id="narration-type"
                value={narrationType}
                onChange={(e) =>
                  setNarrationType(e.target.value as NarrationType)
                }
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
                disabled={loading}
              >
                <option value={NarrationType.SHORT_DRAMA}>短剧解说</option>
              </select>
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
