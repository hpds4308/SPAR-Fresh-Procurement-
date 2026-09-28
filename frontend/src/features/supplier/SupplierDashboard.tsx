import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import DashboardShell from "../shared/DashboardShell";
import { SidebarItem } from "../shared/Sidebar";
import { IconTag, IconClock, IconBranches, IconChat, IconLog, IconUser, IconShield } from "../shared/Icons";
import { fetchMyUnreadCount } from "../../api/messages";
import { fetchMyPendingCount } from "../../api/priceApprovals";
import PriceForm from "./PriceForm";
import PriceHistory from "./PriceHistory";
import PriceApprovals from "./PriceApprovals";
import OrdersByBranch from "./OrdersByBranch";
import SupplierMessages from "./SupplierMessages";
import SupplierGuidelines from "./SupplierGuidelines";
import SupplierAccount from "./SupplierAccount";
import WelcomeScreen from "./WelcomeScreen";
import { FadeSwitch } from "../shared/ui/FadeSwitch";

type Tab = "submit" | "history" | "approvals" | "byBranch" | "messages" | "guidelines" | "account";

const iconProps = { width: 17, height: 17 };
const UNREAD_POLL_MS = 15000;

export default function SupplierDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("submit");
  const [refreshKey, setRefreshKey] = useState(0);
  const [unread, setUnread] = useState(0);
  // Price sheets from SPAR waiting for this supplier's signature.
  const [pendingSheets, setPendingSheets] = useState(0);
  // Set by AuthContext.login() only for a fresh SUPPLIER login, not on a
  // page refresh — read once, then cleared, so it never reappears until
  // the next login.
  const [showWelcome, setShowWelcome] = useState(
    () => sessionStorage.getItem("spar_welcome_pending") === "1"
  );

  useEffect(() => {
    if (showWelcome) sessionStorage.removeItem("spar_welcome_pending");
  }, [showWelcome]);

  useEffect(() => {
    let cancelled = false;
    function poll() {
      fetchMyUnreadCount()
        .then((r) => {
          if (!cancelled) setUnread(r.count);
        })
        .catch(() => {});
      fetchMyPendingCount()
        .then((r) => {
          if (!cancelled) setPendingSheets(r.count);
        })
        .catch(() => {});
    }
    poll();
    const id = setInterval(poll, UNREAD_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (tab !== "messages") return;
    const t = setTimeout(() => {
      fetchMyUnreadCount()
        .then((r) => setUnread(r.count))
        .catch(() => {});
    }, 1200);
    return () => clearTimeout(t);
  }, [tab]);

  const navItems: SidebarItem<Tab>[] = [
    { id: "submit", label: "Submit Prices", icon: <IconTag {...iconProps} /> },
    { id: "history", label: "My Submitted Prices", icon: <IconClock {...iconProps} /> },
    { id: "approvals", label: "Price Approvals", icon: <IconShield {...iconProps} />, badge: pendingSheets },
    { id: "byBranch", label: "Orders by Branch", icon: <IconBranches {...iconProps} /> },
    { id: "messages", label: "Messages", icon: <IconChat {...iconProps} />, badge: unread },
    { id: "guidelines", label: "Supplier Guidelines", icon: <IconLog {...iconProps} /> },
    { id: "account", label: "Account", icon: <IconUser {...iconProps} /> },
  ];

  if (showWelcome) {
    return (
      <WelcomeScreen
        supplierName={user?.supplier_name ?? "Supplier"}
        onContinue={() => setShowWelcome(false)}
      />
    );
  }

  return (
    <DashboardShell
      title="Supplier Dashboard"
      subtitle={user?.supplier_name ? `Supplier: ${user.supplier_name}` : "Supplier user"}
      navItems={navItems}
      activeNav={tab}
      onNavChange={setTab}
      unreadCount={unread}
      onBellClick={() => setTab("messages")}
    >
      {/* Shown on every other tab — on a phone the sidebar badge is hidden behind the menu button. */}
      {pendingSheets > 0 && tab !== "approvals" && (
        <button
          onClick={() => setTab("approvals")}
          className="no-print w-full text-left mb-4 rounded-2xl bg-mango-500/15 border border-mango-500/30 px-4 py-3 text-sm text-[#8A5A0D] hover:bg-mango-500/20 transition-colors"
        >
          SPAR has adjusted your prices — {pendingSheets} price sheet{pendingSheets === 1 ? "" : "s"} waiting for your
          signature. <span className="font-semibold underline">Review &amp; sign</span>
        </button>
      )}
      <FadeSwitch tabKey={tab}>
        {tab === "submit" && <PriceForm onSubmitted={() => setRefreshKey((k) => k + 1)} />}
        {tab === "history" && <PriceHistory refreshKey={refreshKey} />}
        {tab === "approvals" && (
          <PriceApprovals
            onChanged={() => {
              setRefreshKey((k) => k + 1);
              fetchMyPendingCount()
                .then((r) => setPendingSheets(r.count))
                .catch(() => {});
            }}
          />
        )}
        {tab === "byBranch" && <OrdersByBranch />}
        {tab === "messages" && <SupplierMessages />}
        {tab === "guidelines" && <SupplierGuidelines />}
        {tab === "account" && <SupplierAccount />}
      </FadeSwitch>
    </DashboardShell>
  );
}
