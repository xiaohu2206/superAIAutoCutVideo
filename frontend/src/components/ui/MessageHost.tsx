import { AlertCircle, AlertTriangle, CheckCircle, Info, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { messageEventName, type MessageEventDetail, type MessageType } from "../../services/message";

type MessageItem = MessageEventDetail & { createdAt: number };

function getTypeClassName(type: MessageType): string {
  if (type === "success") return "border-green-200 text-green-700 bg-green-50";
  if (type === "error") return "border-red-200 text-red-700 bg-red-50";
  if (type === "warning") return "border-amber-200 text-amber-700 bg-amber-50";
  return "border-blue-200 text-blue-700 bg-blue-50";
}

function getTypeIcon(type: MessageType) {
  if (type === "success") return <CheckCircle className="h-5 w-5" />;
  if (type === "error") return <AlertCircle className="h-5 w-5" />;
  if (type === "warning") return <AlertTriangle className="h-5 w-5" />;
  if (type === "loading") return <Loader2 className="h-5 w-5 animate-spin" />;
  return <Info className="h-5 w-5" />;
}

export default function MessageHost() {
  const [current, setCurrent] = useState<MessageItem | null>(null);

  useEffect(() => {
    const handler = (event: Event) => {
      const e = event as CustomEvent<MessageEventDetail>;
      const detail = e.detail;
      if (!detail || !detail.id) return;
      
      // 设置新消息，直接替换旧消息
      setCurrent({ ...detail, createdAt: Date.now() });
      
      // 注意：已移除自动定时关闭逻辑，实现持久化显示
      // 只有点击关闭按钮或新消息到来时，当前消息才会消失/被替换
    };

    window.addEventListener(messageEventName, handler as EventListener);
    return () => {
      window.removeEventListener(messageEventName, handler as EventListener);
    };
  }, []);

  if (!current) return null;

  return (
    <div
      className={`border shadow-md rounded-lg px-4 py-3 flex items-start gap-3 w-full transition-all duration-300 ${getTypeClassName(current.type)}`}
      role="status"
      aria-live="polite"
    >
      <span className="flex-shrink-0 mt-0.5">{getTypeIcon(current.type)}</span>
      <div className="text-sm flex-1 break-words leading-relaxed pt-0.5">{current.content}</div>
      <button 
        onClick={() => setCurrent(null)}
        className="flex-shrink-0 text-gray-400 hover:text-gray-600 focus:outline-none transition-colors ml-2 -mr-1"
        aria-label="关闭"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
