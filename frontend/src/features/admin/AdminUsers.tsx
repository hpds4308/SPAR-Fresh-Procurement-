import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import {
  UserCreated,
  UserListItem,
  activateUser,
  createUser,
  deactivateUser,
  deleteUser,
  fetchUsers,
  resetPassword,
  updateUser,
} from "../../api/users";
import { createBranch } from "../../api/branches";
import { createSupplier } from "../../api/suppliers";
import Button from "../shared/ui/Button";
import EmptyState from "../shared/EmptyState";
import { IconUser } from "../shared/Icons";
import { Modal } from "../shared/ui/Modal";
import { SkeletonTable } from "../shared/ui/Skeleton";
import { useToast } from "../shared/ui/Toast";

type NewPartyType = "BRANCH" | "SUPPLIER";

const ROLE_COLORS: Record<string, string> = {
  ADMIN: "bg-rose-100 text-rose-700",
  BRANCH: "bg-blue-100 text-blue-700",
  SUPPLIER: "bg-teal-100 text-teal-700",
};

function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={`inline-block text-[11px] font-semibold px-2 py-0.5 rounded-full ${
        ROLE_COLORS[role] ?? "bg-sage-100 text-crate-700"
      }`}
    >
      {role}
    </span>
  );
}

export default function AdminUsers() {
  const { show } = useToast();
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createError, setCreateError] = useState<string | null>(null);
  const [created, setCreated] = useState<UserCreated | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const [newPartyType, setNewPartyType] = useState<NewPartyType>("BRANCH");
  const [newBranchName, setNewBranchName] = useState("");
  const [newBranchLocation, setNewBranchLocation] = useState("");
  const [newSupplierName, setNewSupplierName] = useState("");
  const [newSupplierContact, setNewSupplierContact] = useState("");
  const [newSupplierPhone, setNewSupplierPhone] = useState("");
  const [newSupplierEmail, setNewSupplierEmail] = useState("");
  const [newPartySaving, setNewPartySaving] = useState(false);
  const [newPartyError, setNewPartyError] = useState<string | null>(null);
  const [newPartySuccess, setNewPartySuccess] = useState<string | null>(null);

  const [detailUser, setDetailUser] = useState<UserListItem | null>(null);
  const [detailUsername, setDetailUsername] = useState("");
  const [detailPassword, setDetailPassword] = useState("");
  const [detailSaving, setDetailSaving] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailSaved, setDetailSaved] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState<UserListItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [deactivateTarget, setDeactivateTarget] = useState<UserListItem | null>(null);
  const [deactivating, setDeactivating] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  function load() {
    setLoading(true);
    fetchUsers()
      .then((u) => {
        setUsers(u);
        setError(null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load accounts."))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function handleCreateParty() {
    setNewPartyError(null);
    setNewPartySuccess(null);
    setCreateError(null);
    setCreated(null);
    if (newPartyType === "BRANCH" && !newBranchName.trim()) {
      setNewPartyError("Enter a name for the new branch.");
      return;
    }
    if (newPartyType === "SUPPLIER" && !newSupplierName.trim()) {
      setNewPartyError("Enter a name for the new supplier.");
      return;
    }
    setNewPartySaving(true);
    try {
      if (newPartyType === "BRANCH") {
        const branch = await createBranch({
          branch_name: newBranchName.trim(),
          location: newBranchLocation.trim() || undefined,
        });
        setNewPartySuccess(`Branch "${branch.branch_name}" created (${branch.branch_code}).`);
        setNewBranchName("");
        setNewBranchLocation("");
        try {
          setCreated(await createUser({ role: "BRANCH", branch_id: branch.id }));
        } catch (err) {
          setCreateError(
            err instanceof ApiError
              ? `Branch created, but its login couldn't be set up: ${err.message}`
              : "Branch created, but its login couldn't be set up automatically."
          );
        }
      } else {
        const supplier = await createSupplier({
          supplier_name: newSupplierName.trim(),
          contact_person: newSupplierContact.trim() || undefined,
          phone: newSupplierPhone.trim() || undefined,
          email: newSupplierEmail.trim() || undefined,
        });
        setNewPartySuccess(`Supplier "${supplier.supplier_name}" created (${supplier.supplier_code}).`);
        setNewSupplierName("");
        setNewSupplierContact("");
        setNewSupplierPhone("");
        setNewSupplierEmail("");
        try {
          setCreated(await createUser({ role: "SUPPLIER", supplier_id: supplier.id }));
        } catch (err) {
          setCreateError(
            err instanceof ApiError
              ? `Supplier created, but its login couldn't be set up: ${err.message}`
              : "Supplier created, but its login couldn't be set up automatically."
          );
        }
      }
      load();
    } catch (err) {
      setNewPartyError(
        err instanceof ApiError ? err.message : `Could not create that ${newPartyType.toLowerCase()}.`
      );
    } finally {
      setNewPartySaving(false);
    }
  }

  async function handleActivate(u: UserListItem) {
    setBusyId(u.id);
    try {
      await activateUser(u.id);
      setUsers((prev) => prev.map((x) => (x.id === u.id ? { ...x, is_active: true } : x)));
      show("success", `${u.username} activated.`);
    } catch {
      show("error", `Could not activate ${u.username}.`);
    } finally {
      setBusyId(null);
    }
  }

  async function handleConfirmDeactivate() {
    if (!deactivateTarget) return;
    setDeactivating(true);
    setDeactivateError(null);
    try {
      await deactivateUser(deactivateTarget.id);
      setUsers((prev) => prev.map((x) => (x.id === deactivateTarget.id ? { ...x, is_active: false } : x)));
      show("success", `${deactivateTarget.username} deactivated.`);
      setDeactivateTarget(null);
    } catch (err) {
      setDeactivateError(
        err instanceof ApiError ? err.message : `Could not deactivate ${deactivateTarget.username}.`
      );
    } finally {
      setDeactivating(false);
    }
  }

  async function handleReset(u: UserListItem) {
    setBusyId(u.id);
    setCreateError(null);
    try {
      const result = await resetPassword(u.id);
      setCreated(result);
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : `Could not reset ${u.username}'s password.`);
    } finally {
      setBusyId(null);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteUser(deleteTarget.id);
      setUsers((prev) => prev.filter((x) => x.id !== deleteTarget.id));
      show("success", `${deleteTarget.username} deleted.`);
      setDeleteTarget(null);
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : `Could not delete ${deleteTarget.username}.`);
    } finally {
      setDeleting(false);
    }
  }

  function openDetail(u: UserListItem) {
    setDetailUser(u);
    setDetailUsername(u.username);
    setDetailPassword("");
    setDetailError(null);
    setDetailSaved(false);
  }

  function closeDetail() {
    setDetailUser(null);
  }

  async function handleDetailSave() {
    if (!detailUser) return;
    const usernameChanged = detailUsername.trim().toLowerCase() !== detailUser.username;
    const passwordChanged = detailPassword.trim().length > 0;
    if (!usernameChanged && !passwordChanged) {
      setDetailError("Change the username and/or enter a new password first.");
      return;
    }
    setDetailError(null);
    setDetailSaving(true);
    try {
      const updated = await updateUser(detailUser.id, {
        username: usernameChanged ? detailUsername.trim() : undefined,
        password: passwordChanged ? detailPassword.trim() : undefined,
      });
      setUsers((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
      setDetailUser(updated);
      setDetailUsername(updated.username);
      setDetailPassword("");
      setDetailSaved(true);
      setTimeout(() => setDetailSaved(false), 2000);
    } catch (err) {
      setDetailError(err instanceof ApiError ? err.message : "Could not save these changes.");
    } finally {
      setDetailSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-6">
        <h2 className="font-display font-semibold text-lg text-crate-950 mb-1">Add Branch or Supplier</h2>
        <p className="text-sm text-crate-800/50 mb-5">
          Previously new branches/suppliers only entered the system via a CSV loaded on the server —
          creating one here adds it as master data and sets up its login account immediately.
        </p>

        {newPartySuccess && (
          <div className="mb-5 rounded-2xl bg-crate-700/5 border border-crate-700/20 p-4">
            <p className="text-sm text-crate-950">{newPartySuccess}</p>
          </div>
        )}

        <div className="flex gap-1 bg-sage-100 rounded-full p-0.5 w-fit mb-4">
          {(["BRANCH", "SUPPLIER"] as NewPartyType[]).map((pt) => (
            <button
              key={pt}
              onClick={() => {
                setNewPartyType(pt);
                setNewPartyError(null);
              }}
              className={`text-xs font-semibold rounded-full px-4 py-1.5 transition-colors duration-150 ${
                newPartyType === pt ? "bg-white text-crate-950 shadow-sm" : "text-crate-800/50 hover:text-crate-800"
              }`}
            >
              {pt === "BRANCH" ? "New Branch" : "New Supplier"}
            </button>
          ))}
        </div>

        {newPartyType === "BRANCH" ? (
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
                Branch Name
              </label>
              <input
                type="text"
                value={newBranchName}
                onChange={(e) => setNewBranchName(e.target.value)}
                placeholder="e.g. Ratnapura"
                className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm min-w-[12rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
                Location <span className="normal-case font-normal text-crate-800/35">(optional)</span>
              </label>
              <input
                type="text"
                value={newBranchLocation}
                onChange={(e) => setNewBranchLocation(e.target.value)}
                placeholder="e.g. Sabaragamuwa Province"
                className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm min-w-[14rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
              />
            </div>
            <Button onClick={handleCreateParty} loading={newPartySaving}>
              Create Branch
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
                Supplier Name
              </label>
              <input
                type="text"
                value={newSupplierName}
                onChange={(e) => setNewSupplierName(e.target.value)}
                placeholder="e.g. Green Valley Farms"
                className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm min-w-[12rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
                Contact Person <span className="normal-case font-normal text-crate-800/35">(optional)</span>
              </label>
              <input
                type="text"
                value={newSupplierContact}
                onChange={(e) => setNewSupplierContact(e.target.value)}
                className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm min-w-[10rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
                Phone <span className="normal-case font-normal text-crate-800/35">(optional)</span>
              </label>
              <input
                type="text"
                value={newSupplierPhone}
                onChange={(e) => setNewSupplierPhone(e.target.value)}
                className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm min-w-[9rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
                Email <span className="normal-case font-normal text-crate-800/35">(optional)</span>
              </label>
              <input
                type="email"
                value={newSupplierEmail}
                onChange={(e) => setNewSupplierEmail(e.target.value)}
                className="border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm min-w-[11rem] focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
              />
            </div>
            <Button onClick={handleCreateParty} loading={newPartySaving}>
              Create Supplier
            </Button>
          </div>
        )}
        {newPartyError && <p className="text-tomato-600 text-sm mt-3">{newPartyError}</p>}
      </div>

      {created && (
        <div className="rounded-2xl bg-crate-700/5 border border-crate-700/20 p-4">
          <p className="text-sm font-semibold text-crate-950">
            Account: <span className="font-mono">{created.username}</span>
          </p>
          <p className="text-sm text-crate-800/80 mt-1">
            Password:{" "}
            <span className="font-mono font-semibold text-crate-950">{created.temporary_password}</span>
          </p>
          <p className="text-xs text-crate-800/45 mt-1.5">
            This is shown once — share it with the account holder now and have them change it on first
            login.
          </p>
        </div>
      )}
      {createError && <p className="text-tomato-600 text-sm">{createError}</p>}

      <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-hidden">
        {loading ? (
          <SkeletonTable rows={8} columns={6} />
        ) : error ? (
          <div className="p-6 text-tomato-600 text-sm">{error}</div>
        ) : users.length === 0 ? (
          <EmptyState icon={<IconUser width={20} height={20} />} title="No accounts yet" />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-crate-800/40 text-left text-xs uppercase tracking-wide border-b border-sage-100">
                <th className="px-5 py-2.5 font-medium">Username</th>
                <th className="px-4 py-2.5 font-medium">Role</th>
                <th className="px-4 py-2.5 font-medium">Branch / Supplier</th>
                <th className="px-4 py-2.5 font-medium">Last Login</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sage-100">
              {users.map((u, i) => (
                <tr
                  key={u.id}
                  onClick={() => openDetail(u)}
                  className={`cursor-pointer hover:bg-sage-50/60 transition-colors duration-100 motion-safe:animate-fade-up ${
                    u.is_active ? "" : "opacity-50"
                  }`}
                  style={{ animationDuration: "0.3s", animationDelay: `${Math.min(i, 12) * 25}ms`, animationFillMode: "backwards" }}
                >
                  <td className="px-5 py-2.5 font-mono text-crate-950">{u.username}</td>
                  <td className="px-4 py-2.5">
                    <RoleBadge role={u.role} />
                  </td>
                  <td className="px-4 py-2.5 text-crate-800/70">
                    {u.branch_name ?? u.supplier_name ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-crate-800/50 text-xs">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`text-xs font-semibold rounded-full px-2.5 py-0.5 ${
                        u.is_active ? "bg-crate-700/10 text-crate-700" : "bg-sage-200 text-crate-800/50"
                      }`}
                    >
                      {u.is_active ? "Active" : "Deactivated"}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap" onClick={(e) => e.stopPropagation()}>
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={busyId === u.id}
                      onClick={() => handleReset(u)}
                      className="mr-2"
                    >
                      Reset Password
                    </Button>
                    <Button
                      variant={u.is_active ? "danger" : "secondary"}
                      size="sm"
                      loading={busyId === u.id}
                      onClick={() => {
                        if (u.is_active) {
                          setDeactivateError(null);
                          setDeactivateTarget(u);
                        } else {
                          handleActivate(u);
                        }
                      }}
                      className="mr-2"
                    >
                      {u.is_active ? "Deactivate" : "Activate"}
                    </Button>
                    {!u.is_active && (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() => {
                          setDeleteError(null);
                          setDeleteTarget(u);
                        }}
                      >
                        Delete
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal
        open={!!detailUser}
        onClose={closeDetail}
        title="Account Details"
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={closeDetail}>
              Close
            </Button>
            <Button size="sm" loading={detailSaving} onClick={handleDetailSave}>
              Save Changes
            </Button>
          </>
        }
      >
        {detailUser && (
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
                Username
              </label>
              <input
                type="text"
                value={detailUsername}
                onChange={(e) => setDetailUsername(e.target.value)}
                className="w-full border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-colors duration-150"
              />
            </div>

            <div className="flex gap-6 text-sm">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1">Role</p>
                <RoleBadge role={detailUser.role} />
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1">
                  Branch / Supplier
                </p>
                <p className="text-crate-950">{detailUser.branch_name ?? detailUser.supplier_name ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1">Status</p>
                <p className="text-crate-950">{detailUser.is_active ? "Active" : "Deactivated"}</p>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5">
                Current Password
              </label>
              <p className="text-xs text-crate-800/50 mb-2">
                Passwords are encrypted and can never be displayed, by anyone, even here — set a new one
                below to change it.
              </p>
              <input
                type="text"
                value={detailPassword}
                onChange={(e) => setDetailPassword(e.target.value)}
                placeholder="Leave blank to keep the current password"
                className="w-full border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-colors duration-150"
              />
              <p className="text-xs text-crate-800/40 mt-1">At least 8 characters.</p>
            </div>

            {detailError && <p className="text-tomato-600 text-sm">{detailError}</p>}
            {detailSaved && <p className="text-crate-700 text-sm">✓ Saved.</p>}
          </div>
        )}
      </Modal>

      <Modal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Delete Account"
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button variant="danger" size="sm" loading={deleting} onClick={handleDelete}>
              Delete Permanently
            </Button>
          </>
        }
      >
        {deleteTarget && (
          <div className="space-y-3">
            <p className="text-sm text-crate-950">
              Permanently delete <span className="font-mono font-semibold">{deleteTarget.username}</span>{" "}
              ({deleteTarget.branch_name ?? deleteTarget.supplier_name ?? deleteTarget.role})? This cannot
              be undone.
            </p>
            <p className="text-xs text-crate-800/50">
              Accounts with order, price, or message history can't be deleted — this only works for
              accounts that were never actually used.
            </p>
            {deleteError && <p className="text-tomato-600 text-sm">{deleteError}</p>}
          </div>
        )}
      </Modal>

      <Modal
        open={!!deactivateTarget}
        onClose={() => setDeactivateTarget(null)}
        title="Deactivate Account"
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setDeactivateTarget(null)}>
              Cancel
            </Button>
            <Button variant="danger" size="sm" loading={deactivating} onClick={handleConfirmDeactivate}>
              Deactivate
            </Button>
          </>
        }
      >
        {deactivateTarget && (
          <div className="space-y-3">
            <p className="text-sm text-crate-950">
              Deactivate <span className="font-mono font-semibold">{deactivateTarget.username}</span>{" "}
              ({deactivateTarget.branch_name ?? deactivateTarget.supplier_name ?? deactivateTarget.role})?
              They won't be able to sign in until reactivated.
            </p>
            {deactivateError && <p className="text-tomato-600 text-sm">{deactivateError}</p>}
          </div>
        )}
      </Modal>
    </div>
  );
}
