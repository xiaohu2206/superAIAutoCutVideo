import { useCallback, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import {
  HelpCircle,
  KeyRound,
  Link2Off,
  Loader2,
  Monitor,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import { TauriCommands } from "@/services/clients";
import { message } from "@/services/message";
import {
  bindLicense,
  fetchLicenseClientDeviceId,
  fetchMyLicenses,
  getDefaultLicenseClientDeviceName,
  selfUnbindLicense,
  type LicenseRecord,
} from "./licenseApi";

const PLAN_LABEL: Record<string, string> = {
  monthly: "月付",
  half_year: "半年",
  permanent: "永久",
  trial: "试用",
};

const STATUS_LABEL: Record<string, string> = {
  active: "生效中",
  expired: "已过期",
  revoked: "已撤销",
};

function formatPlan(planType: string): string {
  return PLAN_LABEL[planType] ?? planType;
}

function formatStatus(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function isLicenseExpired(expireAt: string | null | undefined): boolean {
  if (!expireAt) return false;
  try {
    return new Date(expireAt).getTime() <= Date.now();
  } catch {
    return false;
  }
}

function getEffectiveStatus(lic: LicenseRecord): string {
  if (lic.status === "active" && isLicenseExpired(lic.expireAt)) {
    return "expired";
  }
  return lic.status;
}

function canOfferSelfUnbind(lic: LicenseRecord): boolean {
  if (lic.status === "revoked") return false;
  if (getEffectiveStatus(lic) === "revoked") return false;
  if (typeof lic.remainingSelfUnbinds === "number" && lic.remainingSelfUnbinds <= 0) {
    return false;
  }
  return true;
}

function isNextSelfUnbindTheRevokeOne(lic: LicenseRecord): boolean {
  if (typeof lic.userSelfUnbindCount === "number" && lic.userSelfUnbindCount >= 2) {
    return true;
  }
  if (typeof lic.remainingSelfUnbinds === "number" && lic.remainingSelfUnbinds === 1) {
    return true;
  }
  return false;
}

function getExpireStatus(lic: LicenseRecord): { color: string; text: string } {
  if (!lic.expireAt) {
    return { color: "text-slate-400", text: "无到期时间" };
  }
  if (lic.status === "revoked") {
    return { color: "text-slate-400", text: "已撤销" };
  }
  if (isLicenseExpired(lic.expireAt)) {
    return { color: "text-red-600", text: "已过期" };
  }
  const remaining = new Date(lic.expireAt).getTime() - Date.now();
  const days = Math.ceil(remaining / (24 * 60 * 60 * 1000));
  if (days <= 7) {
    return { color: "text-amber-600", text: `${days} 天后到期` };
  }
  return { color: "text-green-600", text: "生效中" };
}

interface UserProfileLicensesProps {
  /** 用户 accessToken，与 /api/licenses 鉴权一致 */
  accessToken: string;
}

export default function UserProfileLicenses({ accessToken }: UserProfileLicensesProps) {
  const [list, setList] = useState<LicenseRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [clientDeviceId, setClientDeviceId] = useState("");
  const [clientDeviceLoading, setClientDeviceLoading] = useState(true);
  const [binding, setBinding] = useState(false);
  const [unbindDialog, setUnbindDialog] = useState<LicenseRecord | null>(null);
  const [unbindingId, setUnbindingId] = useState<number | null>(null);

  const refreshClientDevice = useCallback(async () => {
    setClientDeviceLoading(true);
    try {
      setClientDeviceId(await fetchLicenseClientDeviceId());
    } catch {
      setClientDeviceId("");
    } finally {
      setClientDeviceLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshClientDevice();
  }, [refreshClientDevice]);

  const load = useCallback(async () => {
    if (!accessToken.trim()) {
      setList([]);
      setLoading(false);
      setError("未登录，无法加载 License");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchMyLicenses(accessToken);
      setList(rows);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setList([]);
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleBind = async () => {
    const key = keyInput.trim();
    if (!key || !accessToken.trim()) return;
    setBinding(true);
    setError(null);
    try {
      await bindLicense(accessToken, key);
      setKeyInput("");
      void refreshClientDevice();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBinding(false);
    }
  };

  const confirmSelfUnbind = async () => {
    const lic = unbindDialog;
    if (!lic || !accessToken.trim()) return;
    setUnbindingId(lic.id);
    setError(null);
    try {
      const res = await selfUnbindLicense(accessToken, lic.id);
      setUnbindDialog(null);
      await load();
      if (res.licenseRevoked) {
        message.warning("本次为第 3 次自助解绑，该 License 已被吊销，无法再使用。", 5);
      } else {
        message.success(
          `解绑成功。该密钥在您账号下已累计自助解绑 ${res.userSelfUnbindCount} 次（上限 3 次），剩余可自助解绑次数：${res.remainingSelfUnbinds}。`,
          4
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUnbindingId(null);
    }
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/80 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-3">
        <h3 className="flex items-center text-sm font-semibold text-slate-900">
          <span>我的 License</span>
          <button
            onClick={() =>
              TauriCommands.openExternalLink("https://my.feishu.cn/wiki/NI0qwbHftith0kkxhHJcjGlJnRc?from=from_copylink")
            }
            className="ml-2 inline-flex items-center gap-1 text-xs font-normal text-blue-600 hover:text-blue-700"
          >
            <HelpCircle className="h-3.5 w-3.5" />
            查看教程
          </button>
        </h3>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          刷新
        </button>
      </div>

      <div className="border-b border-slate-100 px-5 py-4">
    
        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              type="text"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="粘贴 License Key"
              className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100"
              disabled={binding}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleBind();
              }}
            />
            <button
              type="button"
              onClick={() => void handleBind()}
              disabled={binding || !keyInput.trim()}
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-violet-500 px-4 py-2 text-sm font-medium text-white shadow-sm transition-opacity hover:opacity-95 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {binding ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              绑定
            </button>
          </div>
        </div>
      </div>

      {error ? (
        <div className="px-5 py-3 text-sm text-red-600">{error}</div>
      ) : null}

      <div className="px-5 py-4">
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-400">
            <Loader2 className="h-5 w-5 animate-spin" />
            加载中…
          </div>
        ) : list.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">暂无已绑定的 License</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {list.map((lic) => (
              <li
                key={lic.id}
                className="rounded-xl border border-slate-100 bg-slate-50/40 px-4 py-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white text-slate-500 ring-1 ring-slate-200/80">
                      <KeyRound className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-mono text-xs text-slate-700" title={lic.licenseKey}>
                        {lic.licenseKey}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        ID {lic.id} · {formatPlan(lic.planType)}
                        {typeof lic.remainingSelfUnbinds === "number" ? (
                          <span> · 自助解绑还可 {lic.remainingSelfUnbinds} 次</span>
                        ) : null}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${
                      getEffectiveStatus(lic) === "active"
                        ? "bg-green-50 text-green-700 ring-green-200/80"
                        : getEffectiveStatus(lic) === "expired"
                          ? "bg-amber-50 text-amber-800 ring-amber-200/80"
                          : "bg-slate-100 text-slate-600 ring-slate-200/80"
                    }`}
                  >
                    {formatStatus(getEffectiveStatus(lic))}
                  </span>
                  {canOfferSelfUnbind(lic) ? (
                    <button
                      type="button"
                      onClick={() => setUnbindDialog(lic)}
                      disabled={unbindingId === lic.id}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 hover:text-red-600 disabled:opacity-50"
                    >
                      {unbindingId === lic.id ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Link2Off className="h-3 w-3" />
                      )}
                      解绑
                    </button>
                  ) : null}
                  </div>
                </div>
                <dl className="mt-2 grid grid-cols-1 gap-1 text-xs text-slate-500 sm:grid-cols-2">
                  <div>
                    <dt className="inline text-slate-400">过期：</dt>
                    <dd className={`inline font-medium ${getExpireStatus(lic).color}`}>
                      {formatDateTime(lic.expireAt)}
                      <span className="ml-1 text-[11px]">({getExpireStatus(lic).text})</span>
                    </dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="inline text-slate-400">设备：</dt>
                    <dd className="inline text-slate-600">
                      <span className="inline-flex items-center gap-1">
                        <Monitor className="inline h-3 w-3" />
                        {lic.devices?.length ?? 0} / {lic.maxDevices}
                      </span>
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        )}
      </div>

      {unbindDialog && typeof document !== "undefined"
        ? createPortal(
            <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
              <div
                className="absolute inset-0 bg-black/40 backdrop-blur-sm"
                onClick={() => !unbindingId && setUnbindDialog(null)}
                aria-hidden
              />
              <div
                className="relative w-full max-w-md rounded-2xl border border-slate-200 bg-white shadow-xl"
                role="dialog"
                aria-modal="true"
                aria-labelledby="license-unbind-title"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
                  <div>
                    <h4 id="license-unbind-title" className="text-sm font-semibold text-slate-900">
                      确认自助解绑
                    </h4>
                    <p className="mt-1 text-xs text-slate-500">
                      每个 License 在您账号下最多可自助解绑 3 次；第 3 次完成后密钥将被吊销。
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setUnbindDialog(null)}
                    disabled={unbindingId !== null}
                    className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-50"
                    aria-label="关闭"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                <div className="space-y-3 px-5 py-4 text-sm text-slate-700">
                  <p className="break-all font-mono text-xs text-slate-600">{unbindDialog.licenseKey}</p>
                  {typeof unbindDialog.userSelfUnbindCount === "number" ||
                  typeof unbindDialog.remainingSelfUnbinds === "number" ? (
                    <p className="text-xs text-slate-500">
                      {typeof unbindDialog.userSelfUnbindCount === "number"
                        ? `已累计自助解绑 ${unbindDialog.userSelfUnbindCount} 次（上限 3 次）`
                        : null}
                      {typeof unbindDialog.remainingSelfUnbinds === "number" ? (
                        <>
                          {typeof unbindDialog.userSelfUnbindCount === "number" ? "，" : null}
                          当前还可自助解绑 {unbindDialog.remainingSelfUnbinds} 次
                        </>
                      ) : null}
                    </p>
                  ) : null}
                  {isNextSelfUnbindTheRevokeOne(unbindDialog) ? (
                    <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
                      本次为第 3 次自助解绑，完成后该 License 将被吊销且无法再使用，请谨慎操作。
                    </p>
                  ) : null}
                </div>

                <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4">
                  <button
                    type="button"
                    onClick={() => setUnbindDialog(null)}
                    disabled={unbindingId !== null}
                    className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    onClick={() => void confirmSelfUnbind()}
                    disabled={unbindingId !== null}
                    className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                  >
                    {unbindingId !== null ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Link2Off className="h-4 w-4" />
                    )}
                    确认解绑
                  </button>
                </div>
              </div>
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
