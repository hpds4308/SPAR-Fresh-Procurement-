import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { SupplierAccountUpdate, fetchMyAccount, updateMyAccount } from "../../api/suppliers";
import { useAuth } from "../auth/AuthContext";
import Button from "../shared/ui/Button";
import { PageSpinner } from "../shared/ui/PageSpinner";
import { useToast } from "../shared/ui/Toast";

// Kept in step with SupplierAccountUpdate's validators in backend/app/schemas/supplier.py.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PHONE_RE = /^\+?[0-9][0-9 -]{6,19}$/;

const EMPTY: SupplierAccountUpdate = { supplier_name: "", company_number: "", whatsapp_number: "", email: "" };

const FIELDS: {
  key: keyof SupplierAccountUpdate;
  label: string;
  type: string;
  placeholder: string;
  maxLength: number;
}[] = [
  { key: "supplier_name", label: "Supplier Name", type: "text", placeholder: "e.g. Green Valley Farms", maxLength: 150 },
  { key: "company_number", label: "Company Number", type: "text", placeholder: "e.g. PV 12345", maxLength: 50 },
  { key: "whatsapp_number", label: "WhatsApp Number", type: "tel", placeholder: "e.g. 0771234567", maxLength: 30 },
  { key: "email", label: "E-Mail", type: "email", placeholder: "e.g. orders@company.lk", maxLength: 120 },
];

function validate(form: SupplierAccountUpdate): string | null {
  if (!form.supplier_name.trim()) return "Enter your supplier name.";
  if (!form.company_number.trim()) return "Enter your company number.";
  if (!PHONE_RE.test(form.whatsapp_number.trim()))
    return "Enter a valid WhatsApp number, e.g. 0771234567 or +94771234567.";
  if (!EMAIL_RE.test(form.email.trim())) return "Enter a valid email address.";
  return null;
}

export default function SupplierAccount() {
  const { refreshUser } = useAuth();
  const { show } = useToast();
  const [form, setForm] = useState<SupplierAccountUpdate>(EMPTY);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMyAccount()
      .then((s) => {
        setForm({
          supplier_name: s.supplier_name ?? "",
          company_number: s.company_number ?? "",
          whatsapp_number: s.whatsapp_number ?? "",
          email: s.email ?? "",
        });
        setUpdatedAt(s.account_updated_at);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Could not load your account."))
      .finally(() => setLoading(false));
  }, []);

  async function handleUpdate() {
    const problem = validate(form);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const saved = await updateMyAccount({
        supplier_name: form.supplier_name.trim(),
        company_number: form.company_number.trim(),
        whatsapp_number: form.whatsapp_number.trim(),
        email: form.email.trim(),
      });
      setForm({
        supplier_name: saved.supplier_name,
        company_number: saved.company_number ?? "",
        whatsapp_number: saved.whatsapp_number ?? "",
        email: saved.email ?? "",
      });
      setUpdatedAt(saved.account_updated_at);
      show("success", "Account details updated.");
      refreshUser();
    } catch (err) {
      setError(
        err instanceof ApiError && typeof err.message === "string" && !err.message.startsWith("[object")
          ? err.message
          : "Could not save your details. Check each field and try again."
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <PageSpinner />;

  return (
    <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-6 md:p-8 max-w-2xl">
      <h2 className="font-display font-semibold text-lg text-crate-950 mb-1">Account</h2>
      <p className="text-sm text-crate-800/50 mb-6">
        Keep your details up to date — SPAR admins use them to contact you.
      </p>

      {loadError ? (
        <p className="text-tomato-600 text-sm">{loadError}</p>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            {FIELDS.map((f) => (
              <div key={f.key}>
                <label
                  htmlFor={`account-${f.key}`}
                  className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5"
                >
                  {f.label}
                </label>
                <input
                  id={`account-${f.key}`}
                  type={f.type}
                  value={form[f.key]}
                  maxLength={f.maxLength}
                  placeholder={f.placeholder}
                  onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                  className="w-full border border-sage-300 bg-sage-50/60 rounded-full px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-crate-700/30 focus:border-crate-700 focus:bg-white transition-all duration-150"
                />
              </div>
            ))}
          </div>

          {error && <p className="text-tomato-600 text-sm mt-4">{error}</p>}

          <div className="flex flex-wrap items-center gap-4 mt-6">
            <Button onClick={handleUpdate} loading={saving}>
              Update
            </Button>
            <p className="text-xs text-crate-800/45">
              {updatedAt ? `Last updated ${new Date(updatedAt).toLocaleString()}` : "Not saved yet"}
            </p>
          </div>
        </>
      )}
    </div>
  );
}
