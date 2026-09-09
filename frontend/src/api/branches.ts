import { apiFetch } from "./client";

export type Branch = {
  id: number;
  branch_code: string;
  branch_name: string;
  location: string | null;
  pos_location_code: string | null;
  status: string;
};

export function fetchBranches(): Promise<Branch[]> {
  return apiFetch("/branches");
}

export function createBranch(payload: {
  branch_name: string;
  branch_code?: string;
  location?: string;
}): Promise<Branch> {
  return apiFetch("/branches", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type OrderDeadlineException = {
  branch_id: number;
  branch_name: string;
  order_date: string;
  granted_by_username: string;
  created_at: string;
};

// Every branch currently allowed to submit an order past today's normal
// cutoff, for one order_date — usually today.
export function fetchOrderDeadlineExceptions(orderDate: string): Promise<OrderDeadlineException[]> {
  return apiFetch(`/branches/order-deadline-exceptions?order_date=${orderDate}`);
}

// Lets one branch submit (or keep editing) its order past today's normal
// cutoff, for one order_date — a one-time exception, not a change to the
// cutoff itself. Safe to call again for the same branch/date.
export function grantOrderDeadlineException(branchId: number, orderDate: string): Promise<{ detail: string }> {
  return apiFetch(`/branches/${branchId}/order-deadline-exception`, {
    method: "POST",
    body: JSON.stringify({ order_date: orderDate }),
  });
}

export function revokeOrderDeadlineException(branchId: number, orderDate: string): Promise<{ detail: string }> {
  return apiFetch(`/branches/${branchId}/order-deadline-exception?order_date=${orderDate}`, {
    method: "DELETE",
  });
}
