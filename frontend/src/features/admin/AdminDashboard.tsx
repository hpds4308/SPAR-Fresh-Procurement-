import { ReactNode, useEffect, useState } from "react";
import DashboardShell from "../shared/DashboardShell";
import { SidebarItem } from "../shared/Sidebar";
import { IconBasket, IconTruck, IconTag, IconChart, IconChat, IconClock, IconGrid, IconStore, IconBranches, IconLog, IconSettings, IconUser } from "../shared/Icons";
import { fetchAdminUnreadCount } from "../../api/messages";
import OrderMatrixView from "./OrderMatrixView";
import AdminOrderHistory from "./AdminOrderHistory";
import ReportsView from "./ReportsView";
import SupplierOrderBuilder from "./SupplierOrderBuilder";
import SupplierPricesView from "./SupplierPricesView";
import AdminKeellsPrices from "./AdminKeellsPrices";
import AdminMarketPrices from "./AdminMarketPrices";
import AdminMarketPriceHistory from "./AdminMarketPriceHistory";
import AdminMasterData from "./AdminMasterData";
import AdminMessages from "./AdminMessages";
import AdminAuditLog from "./AdminAuditLog";
import AdminSettings from "./AdminSettings";
import AdminUsers from "./AdminUsers";
type Tab = "orders" | "orderHistory" | "supplierOrders" | "supplierPrices" | "keellsPrices" | "marketPrices" | "marketPriceHistory" | "masterData" | "messages" | "reports" | "auditLog" | "settings" | "users";

const iconProps = { width: 17, height: 17 };
const UNREAD_POLL_MS = 15000;

export default function AdminDashboard() {
  const [tab, setTab] = useState<Tab>("orders");
  const [unread, setUnread] = useState(0);

  // Every tab a user has opened this session stays mounted (just hidden)
  // instead of being torn down when they switch away — otherwise any
  // in-progress typing (draft quantities, prices, search filters) on the
  // tab they left would be lost the moment they came back to it, since a
  // fresh instance re-fetches from the server with nothing typed in yet.
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set([tab]));
  useEffect(() => {
    setVisited((prev) => (prev.has(tab) ? prev : new Set(prev).add(tab)));
  }, [tab]);

  // Renders `content` once the tab has ever been opened, then keeps it in
  // the DOM permanently (hidden via CSS, not unmounted) so its component
  // state survives switching away and back. `hidden` alone (not
  // conditional rendering) is what makes that work.
  function keepAlive(id: Tab, content: ReactNode) {
    if (!visited.has(id)) return null;
    return (
      <div key={id} hidden={tab !== id} className={tab === id ? "motion-safe:animate-fade-up" : undefined}>
        {content}
      </div>
    );
  }

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
    { id: "marketPrices", label: "Local Market Prices", icon: <IconBranches {...iconProps} /> },
    { id: "marketPriceHistory", label: "Price History", icon: <IconChart {...iconProps} /> },
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
      {keepAlive(
        "orders",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Branch Orders
          </h2>
          <OrderMatrixView />
        </>
      )}
      {keepAlive(
        "orderHistory",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Order History
          </h2>
          <AdminOrderHistory />
        </>
      )}
      {keepAlive(
        "supplierOrders",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Give an order to a supplier
          </h2>
          <SupplierOrderBuilder />
        </>
      )}
      {keepAlive(
        "supplierPrices",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Supplier Prices
          </h2>
          <SupplierPricesView />
        </>
      )}
      {keepAlive(
        "keellsPrices",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Keells Prices
          </h2>
          <AdminKeellsPrices />
        </>
      )}
      {keepAlive(
        "marketPrices",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Local Market Prices
          </h2>
          <AdminMarketPrices />
        </>
      )}
      {keepAlive(
        "marketPriceHistory",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Price History
          </h2>
          <AdminMarketPriceHistory />
        </>
      )}
      {keepAlive(
        "masterData",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Master Data Sheet
          </h2>
          <AdminMasterData />
        </>
      )}
      {keepAlive(
        "messages",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Messages
          </h2>
          <AdminMessages />
        </>
      )}
      {keepAlive("reports", <ReportsView />)}
      {keepAlive(
        "auditLog",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Audit Log
          </h2>
          <AdminAuditLog />
        </>
      )}
      {keepAlive("users", <AdminUsers />)}
      {keepAlive("settings", <AdminSettings />)}
    </DashboardShell>
  );
}
