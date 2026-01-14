export type MessageType = "success" | "error" | "info" | "warning" | "loading";

export interface MessageOpenOptions {
  type?: MessageType;
  content: string;
  duration?: number;
  key?: string;
}

export interface MessageEventDetail {
  id: string;
  type: MessageType;
  content: string;
  duration: number;
}

const EVENT_NAME = "__app_message__";

function createId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function emit(detail: MessageEventDetail) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<MessageEventDetail>(EVENT_NAME, { detail }));
}

function open(options: MessageOpenOptions): string {
  const id = options.key || createId();
  const type: MessageType = options.type || "info";
  const duration = typeof options.duration === "number" ? options.duration : 2;
  emit({ id, type, content: options.content, duration });
  return id;
}

export const message = {
  open,
  success(content: string, duration: number = 2) {
    return open({ type: "success", content, duration });
  },
  error(content: string, duration: number = 3) {
    return open({ type: "error", content, duration });
  },
  info(content: string, duration: number = 2) {
    return open({ type: "info", content, duration });
  },
  warning(content: string, duration: number = 2.5) {
    return open({ type: "warning", content, duration });
  },
  loading(content: string, duration: number = 0) {
    return open({ type: "loading", content, duration });
  },
};

export const messageEventName = EVENT_NAME;

