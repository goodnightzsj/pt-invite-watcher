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

export type SiteTemplate =
  | "nexusphp"
  | "custom"
  | "mteam"
  | "unit3d"
  | "gazelle"
  | "discuz"
  | "tnode";

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
  moviepilot_source?: string;
  moviepilot_cache_fetched_at?: string | null;
  moviepilot_cache_age_seconds?: number | null;
  moviepilot_cache_expired?: boolean | null;
};

export type RegistrySite = {
  id: string;
  name: string;
  aliases: string[];
  domains: string[];
  primary_domain: string;
  primary_url: string;
  schema: SiteTemplate;
  tags: string[];
  registration_path: string;
  invite_path: string;
  notes: string;
};

export type RegistryResponse = {
  items: RegistrySite[];
  total: number;
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

export class HttpError extends Error {
  status: number;
  statusText: string;
  bodyText: string;
  url: string;

  constructor(status: number, statusText: string, bodyText: string, url: string) {
    super(`${status} ${statusText}: ${bodyText.slice(0, 200)}`);
    this.name = "HttpError";
    this.status = status;
    this.statusText = statusText;
    this.bodyText = bodyText;
    this.url = url;
  }
}

import { apiUrl, authHeader, resetRuntimeConfig, runtimeConfig } from "./runtime_config";

// Coalesce a burst of 401s (multiple concurrent requests all failing on the
// same stale session) into a single re-onboard flow — otherwise we'd toast
// "authentication expired" N times and try to reload N times.
let authFailureHandled = false;

function handleAuthFailure(): void {
  if (authFailureHandled) return;
  if (runtimeConfig.mode !== "remote" || !runtimeConfig.basicAuth) return;
  authFailureHandled = true;
  // Clear the bad credentials so `needsOnboarding()` flips to true on reload,
  // landing the user back on the URL + BasicAuth form where they can re-enter.
  resetRuntimeConfig();
  try {
    // Deferred import so this module doesn't pull toast into every chunk.
    import("./toast").then(({ showToast }) => {
      showToast("认证失效，请重新连接服务器", "error", 4000);
    });
  } catch {
    /* ignore — toast is a nicety, the reload is the essential part */
  }
  // Give the toast a moment to render before blowing away the page.
  setTimeout(() => window.location.reload(), 1500);
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  // `path` is expected to be the same relative string call sites have always
  // passed (e.g. "/api/dashboard"). `apiUrl` prepends the runtime base if one
  // is set (remote mode / Tauri embedded-sidecar mode) and keeps the string
  // relative otherwise (same-origin browser).
  const url = apiUrl(path);
  const resp = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeader(),
      ...(init?.headers || {}),
    },
  });
  if (!resp.ok) {
    const text = await resp.text();
    // In remote-mode shells (Capacitor / Tauri), a 401 means the stored
    // credentials are no longer valid — typically because the user changed
    // them server-side. Bounce them back to Onboarding instead of stranding
    // them on a dashboard that will keep 401-ing every request.
    if (resp.status === 401) handleAuthFailure();
    throw new HttpError(resp.status, resp.statusText, text, url);
  }
  return (await resp.json()) as T;
}

export const api = {
  dashboard: () => requestJson<DashboardResponse>("/api/dashboard"),
  scanRun: () => requestJson<ScanStatus>("/api/scan/run", { method: "POST" }),
  scanRunOne: (domain: string) => requestJson<ScanStatus>(`/api/scan/run/${encodeURIComponent(domain)}`, { method: "POST" }),
  stateReset: () => requestJson<{ ok: boolean }>("/api/state/reset", { method: "POST" }),
  sitesList: (params: { live?: boolean; force?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.live !== undefined) q.set("live", params.live ? "1" : "0");
    if (params.force !== undefined) q.set("force", params.force ? "1" : "0");
    const qs = q.toString();
    return requestJson<SitesListResponse>(`/api/sites${qs ? `?${qs}` : ""}`);
  },
  sitesUpsert: (payload: unknown) =>
    requestJson<{ ok: boolean; scan_triggered?: boolean; scan_reason?: string }>("/api/sites", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  sitesDelete: (domain: string) => requestJson<{ ok: boolean }>(`/api/sites/${encodeURIComponent(domain)}`, { method: "DELETE" }),
  sitesRegistry: () => requestJson<RegistryResponse>("/api/sites/registry"),
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
  logsList: (params: { category?: string; domain?: string; keyword?: string; limit?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.category) q.set("category", params.category);
    if (params.domain) q.set("domain", params.domain);
    if (params.keyword) q.set("keyword", params.keyword);
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    const qs = q.toString();
    return requestJson<LogsResponse>(`/api/logs${qs ? `?${qs}` : ""}`);
  },
  logsDomains: () => requestJson<{ domains: string[] }>("/api/logs/domains"),
  version: () => requestJson<{ version: string }>("/api/version"),
};
