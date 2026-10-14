import { useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { AdminAccountUpdate, fetchAdminAccount, updateAdminAccount } from "../../api/adminAccount";
import Button from "../shared/ui/Button";
import { PageSpinner } from "../shared/ui/PageSpinner";
import { useToast } from "../shared/ui/Toast";

// Kept in step with AdminAccountUpdate's validators in backend/app/schemas/user.py.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const PHONE_RE = /^\+?[0-9][0-9 -]{6,19}$/;

const FIELDS: { key: keyof AdminAccountUpdate; label: string; type: string; placeholder: string; maxLength: number }[] = [
  { key: "full_name", label: "Name", type: "text", placeholder: "e.g. Nimal Perera", maxLength: 150 },
  { key: "email", label: "E-Mail", type: "email", placeholder: "e.g. procurement@spar.lk", maxLength: 120 },
  { key: "phone", label: "Phone (optional)", type: "tel", placeholder: "e.g. 0771234567", maxLength: 30 },
];

function validate(form: AdminAccountUpdate): string | null {
  if (!form.full_name.trim()) return "Enter your name.";
  if (!EMAIL_RE.test(form.email.trim())) return "Enter a valid email address.";
  if (form.phone.trim() && !PHONE_RE.test(form.phone.trim()))
    return "Enter a valid phone number, e.g. 0771234567 or +94771234567.";
  return null;
}

/** The signed-in Admin's own details — notification emails go to this email. */
export default function AdminAccount() {
  const { show } = useToast();
  const [username, setUsername] = useState("");
  const [form, setForm] = useState<AdminAccountUpdate>({ full_name: "", email: "", phone: "" });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAdminAccount()
      .then((a) => {
        setUsername(a.username);
        setForm({ full_name: a.full_name ?? "", email: a.email ?? "", phone: a.phone ?? "" });
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Could not load your account."))
      .finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    const problem = validate(form);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setSaving(true);
    try {
      const saved = await updateAdminAccount({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
      });
      setForm({ full_name: saved.full_name ?? "", email: saved.email ?? "", phone: saved.phone ?? "" });
      show("success", "Account details saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save your details. Check each field and try again.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <PageSpinner />;

  return (
    <div className="bg-white rounded-2xl shadow-card border border-sage-100 p-6 md:p-8 max-w-2xl">
      <h2 className="font-display font-semibold text-lg text-crate-950 mb-1">My Account</h2>
      <p className="text-sm text-crate-800/50 mb-6">
        Signed in as <strong>{username}</strong>. Notification emails — new messages, suppliers' answers to your
        adjusted prices — go to the email below.
      </p>

      {loadError ? (
        <p className="text-tomato-600 text-sm">{loadError}</p>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2">
            {FIELDS.map((f) => (
              <div key={f.key}>
                <label
                  htmlFor={`admin-account-${f.key}`}
                  className="block text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-1.5"
                >
                  {f.label}
                </label>
                <input
                  id={`admin-account-${f.key}`}
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

          <div className="mt-6">
            <Button onClick={handleSave} loading={saving}>
              Save
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
