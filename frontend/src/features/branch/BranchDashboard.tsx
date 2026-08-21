import { useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import DashboardShell from "../shared/DashboardShell";
import { SidebarItem } from "../shared/Sidebar";
import { IconPlus, IconClock, IconChat, IconLog } from "../shared/Icons";
import { fetchMyUnreadCount } from "../../api/messages";
import OrderForm from "./OrderForm";
import OrderHistory from "./OrderHistory";
import BranchMessages from "./BranchMessages";
import BranchGuidelines from "./BranchGuidelines";
import BranchWelcomeScreen from "./BranchWelcomeScreen";
import { FadeSwitch } from "../shared/ui/FadeSwitch";

type Tab = "new" | "history" | "messages" | "guidelines";

const iconProps = { width: 17, height: 17 };
const UNREAD_POLL_MS = 15000;

export default function BranchDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("new");
  const [refreshKey, setRefreshKey] = useState(0);
  const [unread, setUnread] = useState(0);
  // Set by AuthContext.login() only for a fresh BRANCH login, not on a
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
    { id: "new", label: "New Order", icon: <IconPlus {...iconProps} /> },
    { id: "history", label: "My Orders", icon: <IconClock {...iconProps} /> },
    { id: "messages", label: "Messages", icon: <IconChat {...iconProps} />, badge: unread },
    { id: "guidelines", label: "Branch Guidelines", icon: <IconLog {...iconProps} /> },
  ];

  if (showWelcome) {
    return (
      <BranchWelcomeScreen
        branchName={user?.branch_name ?? "Branch"}
        onContinue={() => setShowWelcome(false)}
      />
    );
  }

  return (
    <DashboardShell
      title="Branch Dashboard"
      subtitle={user?.branch_name ? `Branch: ${user.branch_name}` : "Branch user"}
      navItems={navItems}
      activeNav={tab}
      onNavChange={setTab}
      unreadCount={unread}
      onBellClick={() => setTab("messages")}
    >
      <FadeSwitch tabKey={tab}>
        {tab === "new" && <OrderForm onSubmitted={() => setRefreshKey((k) => k + 1)} />}
        {tab === "history" && <OrderHistory refreshKey={refreshKey} />}
        {tab === "messages" && <BranchMessages />}
        {tab === "guidelines" && <BranchGuidelines />}
      </FadeSwitch>
    </DashboardShell>
  );
}
