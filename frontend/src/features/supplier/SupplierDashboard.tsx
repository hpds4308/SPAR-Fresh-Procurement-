import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import DashboardShell from "../shared/DashboardShell";
import { SidebarItem } from "../shared/Sidebar";
import { IconTag, IconClock, IconBranches, IconChat, IconLog } from "../shared/Icons";
import { fetchMyUnreadCount } from "../../api/messages";
import PriceForm from "./PriceForm";
import PriceHistory from "./PriceHistory";
import OrdersByBranch from "./OrdersByBranch";
import SupplierMessages from "./SupplierMessages";
import SupplierGuidelines from "./SupplierGuidelines";
import WelcomeScreen from "./WelcomeScreen";
import { FadeSwitch } from "../shared/ui/FadeSwitch";

type Tab = "submit" | "history" | "byBranch" | "messages" | "guidelines";

const iconProps = { width: 17, height: 17 };
const UNREAD_POLL_MS = 15000;

export default function SupplierDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("submit");
  const [refreshKey, setRefreshKey] = useState(0);
  const [unread, setUnread] = useState(0);
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
    { id: "byBranch", label: "Orders by Branch", icon: <IconBranches {...iconProps} /> },
    { id: "messages", label: "Messages", icon: <IconChat {...iconProps} />, badge: unread },
    { id: "guidelines", label: "Supplier Guidelines", icon: <IconLog {...iconProps} /> },
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
      <FadeSwitch tabKey={tab}>
        {tab === "submit" && <PriceForm onSubmitted={() => setRefreshKey((k) => k + 1)} />}
        {tab === "history" && <PriceHistory refreshKey={refreshKey} />}
        {tab === "byBranch" && <OrdersByBranch />}
        {tab === "messages" && <SupplierMessages />}
        {tab === "guidelines" && <SupplierGuidelines />}
      </FadeSwitch>
    </DashboardShell>
  );
}
