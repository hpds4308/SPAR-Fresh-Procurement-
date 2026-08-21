import { apiFetch } from "./client";

export type AuditLog = {
  id: number;
  username: string | null;
  role: string | null;
  action: string;
  entity_type: string | null;
  entity_id: number | null;
  description: string | null;
  created_at: string;
};

export function fetchAuditLogs(params: { limit?: number; action?: string; entityType?: string }): Promise<AuditLog[]> {
  const qs = new URLSearchParams();
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.action) qs.set("action", params.action);
  if (params.entityType) qs.set("entity_type", params.entityType);
  const query = qs.toString();
  return apiFetch(`/audit-logs${query ? `?${query}` : ""}`);
}

export function fetchAuditLogActions(): Promise<string[]> {
  return apiFetch("/audit-logs/actions");
}
