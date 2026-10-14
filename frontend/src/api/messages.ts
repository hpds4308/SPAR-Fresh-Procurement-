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

// `count` is the one total badge; the rest split it per Messages tab, plus
// who wrote the newest unread supplier <-> branch message ("Bloomax → Kandy").
export type AdminUnreadCount = {
  count: number;
  suppliers: number;
  branches: number;
  supplier_branch: number;
  latest_supplier_branch: string | null;
  latest_supplier_branch_id: number | null;
};

export function fetchAdminUnreadCount(): Promise<AdminUnreadCount> {
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

// ---- Supplier <-> branch chats ----

// A supplier's chat with one branch, or a branch's chat with one supplier.
// `id` is the branch id for a supplier, the supplier id for a branch.
export type ContactThread = {
  id: number;
  code: string;
  name: string;
  last_message_body: string | null;
  last_message_at: string | null;
  unread_count: number;
};

export function fetchMyContacts(): Promise<ContactThread[]> {
  return apiFetch("/messages/mine/contacts");
}

export function fetchChatWith(otherId: number): Promise<Message[]> {
  return apiFetch(`/messages/mine/with/${otherId}`);
}

export function sendChatMessage(otherId: number, body: string): Promise<Message> {
  return apiFetch(`/messages/mine/with/${otherId}`, {
    method: "POST",
    body: JSON.stringify({ body }),
  });
}

// Admin's read-only view of supplier <-> branch chats.
export type PairConversation = {
  supplier_id: number;
  supplier_name: string;
  branch_id: number;
  branch_name: string;
  message_count: number;
  unread_count: number; // not yet seen by Admin
  last_message_body: string;
  last_message_at: string;
  last_sender_role: "SUPPLIER" | "BRANCH";
};

export function fetchPairConversations(): Promise<PairConversation[]> {
  return apiFetch("/messages/admin/supplier-branch");
}

export function fetchPairConversation(supplierId: number, branchId: number): Promise<Message[]> {
  return apiFetch(`/messages/admin/supplier-branch/${supplierId}/${branchId}`);
}
