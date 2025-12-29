export type ReachabilityState = "up" | "down" | "unknown";
export type State = "open" | "closed" | "unknown";

export type ScanStatus = {
  ok: boolean;
  site_count: number;
  scanned_count?: number;
  skipped_in_flight?: number;
  error: string;
  last_run_at: string;
  warning?: string;
  domain?: string;
  moviepilot_ok?: boolean;
  moviepilot_error?: string;
};

export type SiteRow = {
  domain: string;
  name: string;
  url: string;
  engine: string;
  registration_url?: string;
  invite_url?: string;
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
  scanning?: boolean;
};

export type DashboardResponse = {
  rows: SiteRow[];
  scan_status: ScanStatus | null;
  scan_hint?: { reason: string; at: string; changed?: string[] } | null;
  ui?: { allow_state_reset: boolean } | null;
};

export type LogItem = {
  id: number;
  ts: string;
  category: string;
  level: string;
  action: string;
  domain: string | null;
  message: string;
  detail: any | null;
};

export type LogsResponse = { items: LogItem[] };

export type SiteTemplate = "nexusphp" | "custom" | "mteam";

export type SiteConfigItem = {
  domain: string;
  name: string;
  url: string;
  source: "moviepilot" | "manual";
  template: SiteTemplate;
  has_local_config: boolean;
  reachability_state?: ReachabilityState;
  cookie_configured: boolean;
  authorization_configured: boolean;
  did_configured: boolean;
  registration_url: string;
  invite_url: string;
};

export type SitesListResponse = {
  items: SiteConfigItem[];
  moviepilot_ok: boolean;
  moviepilot_error: string;
};

export type ConfigResponse = {
  moviepilot: {
    base_url: string;
    username: string;
    password_configured: boolean;
    otp_configured: boolean;
    sites_cache_ttl_seconds: number;
  };
  connectivity: {
    retry_interval_seconds: number;
    request_retry_delay_seconds?: number;
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
  ui?: { allow_state_reset: boolean };
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
  scanRunOne: (domain: string) => requestJson<ScanStatus>(`/api/scan/run/${encodeURIComponent(domain)}`, { method: "POST" }),
  stateReset: () => requestJson<{ ok: boolean }>("/api/state/reset", { method: "POST" }),
  sitesList: () => requestJson<SitesListResponse>("/api/sites"),
  sitesUpsert: (payload: unknown) =>
    requestJson<{ ok: boolean; scan_triggered?: boolean; scan_reason?: string }>("/api/sites", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  sitesDelete: (domain: string) => requestJson<{ ok: boolean }>(`/api/sites/${encodeURIComponent(domain)}`, { method: "DELETE" }),
  configGet: () => requestJson<ConfigResponse>("/api/config"),
  configPut: (payload: unknown) => requestJson<{ ok: boolean }>("/api/config", { method: "PUT", body: JSON.stringify(payload) }),
  configReset: () => requestJson<{ ok: boolean }>("/api/config/reset", { method: "POST" }),
  backupExport: (includeSecrets: boolean) =>
    requestJson<any>(`/api/backup/export?include_secrets=${includeSecrets ? 1 : 0}`),
  backupImport: (payload: unknown, mode: "merge" | "replace") =>
    requestJson<{ ok: boolean; message?: string; changed?: string[]; needs_scan?: boolean }>(`/api/backup/import?mode=${mode}`, { method: "POST", body: JSON.stringify(payload) }),
  notificationsGet: () => requestJson<NotificationsResponse>("/api/notifications"),
  notificationsPut: (payload: unknown) =>
    requestJson<{ ok: boolean }>("/api/notifications", { method: "PUT", body: JSON.stringify(payload) }),
  notificationsTest: (channel: "telegram" | "wecom") =>
    requestJson<{ ok: boolean; message: string }>(`/api/notifications/test/${channel}`, { method: "POST" }),
  logsList: (params: { category?: string; keyword?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.category) q.set("category", params.category);
    if (params.keyword) q.set("keyword", params.keyword);
    if (params.limit) q.set("limit", String(params.limit));
    const qs = q.toString();
    return requestJson<LogsResponse>(`/api/logs${qs ? `?${qs}` : ""}`);
  },
  logsClear: () => requestJson<{ ok: boolean }>("/api/logs/clear", { method: "POST" }),
};
