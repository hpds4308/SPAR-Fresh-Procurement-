import { useEffect, useState } from "react";
import DashboardShell from "../shared/DashboardShell";
import { SidebarItem } from "../shared/Sidebar";
import { IconBasket, IconTruck, IconTag, IconChart, IconChat, IconClock, IconGrid, IconStore, IconLog, IconSettings, IconUser } from "../shared/Icons";
import { fetchAdminUnreadCount } from "../../api/messages";
import OrderMatrixView from "./OrderMatrixView";
import AdminOrderHistory from "./AdminOrderHistory";
import ReportsView from "./ReportsView";
import SupplierOrderBuilder from "./SupplierOrderBuilder";
import SupplierPricesView from "./SupplierPricesView";
import AdminKeellsPrices from "./AdminKeellsPrices";
import AdminMasterData from "./AdminMasterData";
import AdminMessages from "./AdminMessages";
import AdminAuditLog from "./AdminAuditLog";
import AdminSettings from "./AdminSettings";
import AdminUsers from "./AdminUsers";
import { FadeSwitch } from "../shared/ui/FadeSwitch";

type Tab = "orders" | "orderHistory" | "supplierOrders" | "supplierPrices" | "keellsPrices" | "masterData" | "messages" | "reports" | "auditLog" | "settings" | "users";

const iconProps = { width: 17, height: 17 };
const UNREAD_POLL_MS = 15000;

export default function AdminDashboard() {
  const [tab, setTab] = useState<Tab>("orders");
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    let cancelled = false;
    function poll() {
      fetchAdminUnreadCount()
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
      fetchAdminUnreadCount()
        .then((r) => setUnread(r.count))
        .catch(() => {});
    }, 1200);
    return () => clearTimeout(t);
  }, [tab]);

  const navItems: SidebarItem<Tab>[] = [
    { id: "orders", label: "Branch Orders", icon: <IconBasket {...iconProps} /> },
    { id: "orderHistory", label: "Order History", icon: <IconClock {...iconProps} /> },
    { id: "supplierOrders", label: "Supplier Orders", icon: <IconTruck {...iconProps} /> },
    { id: "supplierPrices", label: "Supplier Prices", icon: <IconTag {...iconProps} /> },
    { id: "keellsPrices", label: "Keells Prices", icon: <IconStore {...iconProps} /> },
    { id: "masterData", label: "Master Data Sheet", icon: <IconGrid {...iconProps} /> },
    { id: "messages", label: "Messages", icon: <IconChat {...iconProps} />, badge: unread },
    { id: "reports", label: "Reports", icon: <IconChart {...iconProps} /> },
    { id: "auditLog", label: "Audit Log", icon: <IconLog {...iconProps} /> },
    { id: "users", label: "Accounts", icon: <IconUser {...iconProps} /> },
    { id: "settings", label: "Settings", icon: <IconSettings {...iconProps} /> },
  ];

  return (
    <DashboardShell
      title="Admin / Procurement Dashboard"
      subtitle="Central view across all branches and suppliers"
      navItems={navItems}
      activeNav={tab}
      onNavChange={setTab}
      unreadCount={unread}
      onBellClick={() => setTab("messages")}
    >
      <FadeSwitch tabKey={tab}>
        {tab === "orders" && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
              Branch Orders
            </h2>
            <OrderMatrixView />
          </>
        )}
        {tab === "orderHistory" && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
              Order History
            </h2>
            <AdminOrderHistory />
          </>
        )}
        {tab === "supplierOrders" && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
              Give an order to a supplier
            </h2>
            <SupplierOrderBuilder />
          </>
        )}
        {tab === "supplierPrices" && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
              Supplier Prices
            </h2>
            <SupplierPricesView />
          </>
        )}
        {tab === "keellsPrices" && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
              Keells Prices
            </h2>
            <AdminKeellsPrices />
          </>
        )}
        {tab === "masterData" && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
              Master Data Sheet
            </h2>
            <AdminMasterData />
          </>
        )}
        {tab === "messages" && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
              Messages
            </h2>
            <AdminMessages />
          </>
        )}
        {tab === "reports" && <ReportsView />}
        {tab === "auditLog" && (
          <>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
              Audit Log
            </h2>
            <AdminAuditLog />
          </>
        )}
        {tab === "users" && <AdminUsers />}
        {tab === "settings" && <AdminSettings />}
      </FadeSwitch>
    </DashboardShell>
  );
}
