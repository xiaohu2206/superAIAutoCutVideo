import { TauriCommands } from "./tauriService";

export async function notifyError(title: string, error: any, fallback?: string): Promise<string> {
  let message = fallback || "操作失败";
  if (error) {
    if (typeof error === "string") {
      message = error;
    } else if (error.message) {
      message = error.message;
    } else if (error.detail) {
      message = error.detail;
    } else if (typeof error.toString === "function") {
      message = error.toString();
    }
  }
  await TauriCommands.showNotification(title, message);
  return message;
}

export async function notifySuccess(title: string, message: string): Promise<void> {
  await TauriCommands.showNotification(title, message);
}
