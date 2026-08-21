import { apiFetch } from "./client";

export type Message = {
  id: number;
  supplier_id: number | null;
  branch_id: number | null;
  sender_role: "ADMIN" | "SUPPLIER" | "BRANCH";
  sender_username: string;
  body: string;
  created_at: string;
};

export type SupplierThread = {
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  last_message_body: string | null;
  last_message_at: string | null;
  unread_count: number;
};

export type BranchThread = {
  branch_id: number;
  branch_code: string;
  branch_name: string;
  last_message_body: string | null;
  last_message_at: string | null;
  unread_count: number;
};

// ---- Admin ----

export function fetchAdminThreads(): Promise<SupplierThread[]> {
  return apiFetch("/messages/admin/threads");
}

export function fetchAdminUnreadCount(): Promise<{ count: number }> {
  return apiFetch("/messages/admin/unread-count");
}

export function fetchAdminThread(supplierId: number): Promise<Message[]> {
  return apiFetch(`/messages/admin/${supplierId}`);
}

export function sendAdminMessage(supplierId: number, body: string): Promise<Message> {
  return apiFetch(`/messages/admin/${supplierId}`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function fetchAdminBranchThreads(): Promise<BranchThread[]> {
  return apiFetch("/messages/admin/branch-threads");
}

export function fetchAdminBranchThread(branchId: number): Promise<Message[]> {
  return apiFetch(`/messages/admin/branch/${branchId}`);
}

export function sendAdminBranchMessage(branchId: number, body: string): Promise<Message> {
  return apiFetch(`/messages/admin/branch/${branchId}`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

// ---- Supplier / Branch (each has exactly one thread, with Admin) ----

export function fetchMyThread(): Promise<Message[]> {
  return apiFetch("/messages/mine");
}

export function sendMyMessage(body: string): Promise<Message> {
  return apiFetch("/messages/mine", {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

export function fetchMyUnreadCount(): Promise<{ count: number }> {
  return apiFetch("/messages/mine/unread-count");
}
