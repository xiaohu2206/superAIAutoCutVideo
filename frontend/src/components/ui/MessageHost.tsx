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
  const [items, setItems] = useState<MessageItem[]>([]);
  const timersRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    const removeById = (id: string) => {
      setItems((prev) => prev.filter((x) => x.id !== id));
      const t = timersRef.current.get(id);
      if (t) {
        window.clearTimeout(t);
        timersRef.current.delete(id);
      }
    };

    const handler = (event: Event) => {
      const e = event as CustomEvent<MessageEventDetail>;
      const detail = e.detail;
      if (!detail || !detail.id) return;
      setItems((prev) => {
        const next: MessageItem[] = [...prev, { ...detail, createdAt: Date.now() }];
        if (next.length > 5) return next.slice(next.length - 5);
        return next;
      });

      if (typeof detail.duration === "number" && detail.duration > 0) {
        const timeoutId = window.setTimeout(() => removeById(detail.id), Math.round(detail.duration * 1000));
        timersRef.current.set(detail.id, timeoutId);
      }
    };

    window.addEventListener(messageEventName, handler as EventListener);
    return () => {
      window.removeEventListener(messageEventName, handler as EventListener);
      timersRef.current.forEach((t) => window.clearTimeout(t));
      timersRef.current.clear();
    };
  }, []);

  if (items.length === 0) return null;

  return (
    <div className="fixed top-4 left-1/2 -translate-x-1/2 z-[9999] space-y-2 pointer-events-none">
      {items.map((it) => (
        <div
          key={it.id}
          className={`pointer-events-none bg-white border shadow-sm rounded-lg px-4 py-2 flex items-center gap-2 min-w-[240px] max-w-[560px] ${getTypeClassName(it.type)}`}
          role="status"
          aria-live="polite"
        >
          <span className="flex-shrink-0">{getTypeIcon(it.type)}</span>
          <div className="text-sm break-words">{it.content}</div>
        </div>
      ))}
    </div>
  );
}
