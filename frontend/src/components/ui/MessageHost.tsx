import { AlertCircle, AlertTriangle, CheckCircle, Info, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { messageEventName, type MessageEventDetail, type MessageType } from "../../services/message";

type MessageItem = MessageEventDetail & { createdAt: number };

function getTypeClassName(type: MessageType): string {
  if (type === "success") return "border-green-200 text-green-700";
  if (type === "error") return "border-red-200 text-red-700";
  if (type === "warning") return "border-amber-200 text-amber-700";
  return "border-blue-200 text-blue-700";
}

function getTypeIcon(type: MessageType) {
  if (type === "success") return <CheckCircle className="h-4 w-4" />;
  if (type === "error") return <AlertCircle className="h-4 w-4" />;
  if (type === "warning") return <AlertTriangle className="h-4 w-4" />;
  if (type === "loading") return <Loader2 className="h-4 w-4 animate-spin" />;
  return <Info className="h-4 w-4" />;
}

export default function MessageHost() {
  const [current, setCurrent] = useState<MessageItem | null>(null);
  const timersRef = useRef<number | null>(null);

  useEffect(() => {
    const handler = (event: Event) => {
      const e = event as CustomEvent<MessageEventDetail>;
      const detail = e.detail;
      if (!detail || !detail.id) return;
      setCurrent({ ...detail, createdAt: Date.now() });
      if (timersRef.current) {
        window.clearTimeout(timersRef.current);
        timersRef.current = null;
      }
      if (typeof detail.duration === "number" && detail.duration > 0) {
        timersRef.current = window.setTimeout(() => setCurrent(null), Math.round(detail.duration * 1000));
      }
    };

    window.addEventListener(messageEventName, handler as EventListener);
    return () => {
      window.removeEventListener(messageEventName, handler as EventListener);
      if (timersRef.current) {
        window.clearTimeout(timersRef.current);
        timersRef.current = null;
      }
    };
  }, []);

  if (!current) return null;

  return (
    <div
      className={`bg-white border shadow-sm rounded-lg px-4 py-2 flex items-center gap-2 w-full ${getTypeClassName(current.type)}`}
      role="status"
      aria-live="polite"
    >
      <span className="flex-shrink-0">{getTypeIcon(current.type)}</span>
      <div className="text-sm truncate flex-1 whitespace-nowrap">{current.content}</div>
    </div>
  );
}
