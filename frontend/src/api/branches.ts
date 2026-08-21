import { apiFetch } from "./client";

export type Branch = {
  id: number;
  branch_code: string;
  branch_name: string;
  location: string | null;
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
