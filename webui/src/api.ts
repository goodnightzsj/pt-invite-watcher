export type ReachabilityState = "up" | "down" | "unknown";
export type State = "open" | "closed" | "unknown";

export type ScanStatus = {
  ok: boolean;
  site_count: number;
  error: string;
  last_run_at: string;
};

export type SiteRow = {
  domain: string;
  name: string;
  url: string;
  engine: string;
  reachability_state: ReachabilityState;
  reachability_note: string;
  registration_state: State;
  registration_note: string;
  invites_state: State;
  invites_available: number | null;
  invites_display: string;
  last_checked_at: string;
  last_changed_at: string | null;
  errors: string[];
};

export type DashboardResponse = {
  rows: SiteRow[];
  scan_status: ScanStatus | null;
};

export type ConfigResponse = {
  moviepilot: {
    base_url: string;
    username: string;
    password_configured: boolean;
    otp_configured: boolean;
  };
  cookie: {
    source: string;
    cookiecloud: {
      base_url: string;
      uuid: string;
      password_configured: boolean;
      refresh_interval_seconds: number;
    };
  };
  scan: {
    interval_seconds: number;
    timeout_seconds: number;
    concurrency: number;
    user_agent: string;
    trust_env: boolean;
  };
};

export type NotificationsResponse = {
  telegram: { enabled: boolean; configured: boolean; chat_id: string };
  wecom: {
    enabled: boolean;
    configured: boolean;
    corpid: string;
    agent_id: string;
    to_user: string;
    to_party: string;
    to_tag: string;
  };
};

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status} ${resp.statusText}: ${text.slice(0, 200)}`);
  }
  return (await resp.json()) as T;
}

export const api = {
  dashboard: () => requestJson<DashboardResponse>("/api/dashboard"),
  scanRun: () => requestJson<ScanStatus>("/api/scan/run", { method: "POST" }),
  configGet: () => requestJson<ConfigResponse>("/api/config"),
  configPut: (payload: unknown) => requestJson<{ ok: boolean }>("/api/config", { method: "PUT", body: JSON.stringify(payload) }),
  configReset: () => requestJson<{ ok: boolean }>("/api/config/reset", { method: "POST" }),
  notificationsGet: () => requestJson<NotificationsResponse>("/api/notifications"),
  notificationsPut: (payload: unknown) =>
    requestJson<{ ok: boolean }>("/api/notifications", { method: "PUT", body: JSON.stringify(payload) }),
  notificationsTest: (channel: "telegram" | "wecom") =>
    requestJson<{ ok: boolean; message: string }>(`/api/notifications/test/${channel}`, { method: "POST" }),
};

