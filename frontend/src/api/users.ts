import { apiFetch } from "./client";

export type UserListItem = {
  id: number;
  username: string;
  role: string;
  branch_name: string | null;
  supplier_name: string | null;
  is_active: boolean;
  last_login_at: string | null;
};

export type AvailableParty = {
  id: number;
  code: string;
  name: string;
};

export type UserCreated = {
  id: number;
  username: string;
  role: string;
  temporary_password: string;
};

export function fetchUsers(): Promise<UserListItem[]> {
  return apiFetch("/users");
}

export function fetchAvailableBranches(): Promise<AvailableParty[]> {
  return apiFetch("/users/available-branches");
}

export function fetchAvailableSuppliers(): Promise<AvailableParty[]> {
  return apiFetch("/users/available-suppliers");
}

export function createUser(payload: {
  role: "ADMIN" | "BRANCH" | "SUPPLIER";
  branch_id?: number;
  supplier_id?: number;
  username?: string;
}): Promise<UserCreated> {
  return apiFetch("/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resetPassword(userId: number): Promise<UserCreated> {
  return apiFetch(`/users/${userId}/reset-password`, { method: "POST" });
}

export function updateUser(
  userId: number,
  payload: { username?: string; password?: string }
): Promise<UserListItem> {
  return apiFetch(`/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function activateUser(userId: number): Promise<{ detail: string }> {
  return apiFetch(`/users/${userId}/activate`, { method: "POST" });
}

export function deleteUser(userId: number): Promise<{ detail: string }> {
  return apiFetch(`/users/${userId}`, { method: "DELETE" });
}

export function deactivateUser(userId: number): Promise<{ detail: string }> {
  return apiFetch(`/users/${userId}/deactivate`, { method: "POST" });
}
