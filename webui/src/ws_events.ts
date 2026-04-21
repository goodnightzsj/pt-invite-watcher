export const WS_CONNECTED = "connected" as const;
export const WS_PING = "ping" as const;
export const WS_DASHBOARD_UPDATE = "dashboard_update" as const;
export const WS_LOGS_UPDATE = "logs_update" as const;
export const WS_LOGS_APPEND = "logs_append" as const;
export const WS_SCAN_PROGRESS = "scan_progress" as const;

export type WSEventType =
  | typeof WS_CONNECTED
  | typeof WS_PING
  | typeof WS_DASHBOARD_UPDATE
  | typeof WS_LOGS_UPDATE
  | typeof WS_LOGS_APPEND
  | typeof WS_SCAN_PROGRESS;

