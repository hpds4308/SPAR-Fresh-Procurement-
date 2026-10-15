import { ReactNode, useEffect, useRef, useState } from "react";
import DashboardShell from "../shared/DashboardShell";
import { useTabParam } from "../shared/useTabParam";
import { SidebarItem } from "../shared/Sidebar";
import { IconTruck, IconChart, IconChat, IconGrid, IconStore, IconBranches, IconSettings } from "../shared/Icons";
import { CountBadge } from "../shared/ui/Badge";
import { fetchAdminUnreadCount } from "../../api/messages";
import { fetchAdminAttentionCount } from "../../api/priceApprovals";
import { fetchUnreviewedAutoOrders } from "../../api/orders";
import { useToast } from "../shared/ui/Toast";
import OrderMatrixView from "./OrderMatrixView";
import AdminOrderHistory from "./AdminOrderHistory";
import ReportsView from "./ReportsView";
import SupplierOrderBuilder from "./SupplierOrderBuilder";
import AdminPurchaseOrders, { PoFocus } from "./AdminPurchaseOrders";
import SupplierPricesView from "./SupplierPricesView";
import AdminSupplierPriceHistory from "./AdminSupplierPriceHistory";
import AdminPriceApprovals from "./AdminPriceApprovals";
import AdminKeellsPrices from "./AdminKeellsPrices";
import AdminMarketPrices from "./AdminMarketPrices";
import AdminMarketPriceHistory from "./AdminMarketPriceHistory";
import AdminMasterData from "./AdminMasterData";
import AdminPromotions from "./AdminPromotions";
import AdminProductList from "./AdminProductList";
import AdminMessages from "./AdminMessages";
import AdminAuditLog from "./AdminAuditLog";
import AdminSettings from "./AdminSettings";
import AdminUsers from "./AdminUsers";
import AdminAccount from "./AdminAccount";
const TABS = ["orders", "orderHistory", "supplierPrices", "supplierOrders", "purchaseOrders", "priceApprovals", "supplierPriceHistory", "keellsPrices", "marketPrices", "marketPriceHistory", "masterData", "productList", "promotions", "messages", "reports", "auditLog", "settings", "users", "account"] as const;
type Tab = (typeof TABS)[number];

// The sidebar shows these sections; each one's pages appear as sub-tabs
// across the top of the content. The URL still names the page (?tab=...),
// so links and refreshes land on the exact sub-tab.
const SECTIONS = ["branches", "suppliers", "masterData", "messages", "reports", "competitorPrices", "settings"] as const;
type Section = (typeof SECTIONS)[number];

const SECTION_TABS: Record<Section, { id: Tab; label: string }[]> = {
  branches: [
    { id: "orders", label: "Branch Orders" },
    { id: "orderHistory", label: "Branch Order History" },
  ],
  suppliers: [
    { id: "supplierPrices", label: "Supplier Prices" },
    { id: "supplierOrders", label: "Supplier Orders" },
    { id: "purchaseOrders", label: "Purchase Orders" },
    { id: "priceApprovals", label: "Price Approvals" },
    { id: "supplierPriceHistory", label: "Suppliers Price History" },
  ],
  masterData: [{ id: "masterData", label: "Master Data Sheet" }],
  messages: [{ id: "messages", label: "Messages" }],
  reports: [{ id: "reports", label: "Reports" }],
  competitorPrices: [
    { id: "keellsPrices", label: "Keells Prices" },
    { id: "marketPrices", label: "Local Market Prices" },
    { id: "marketPriceHistory", label: "Price History" },
  ],
  settings: [
    { id: "settings", label: "General" },
    { id: "productList", label: "Product List" },
    { id: "promotions", label: "Promotions" },
    { id: "auditLog", label: "Audit Log" },
    { id: "users", label: "Accounts" },
    { id: "account", label: "My Account" },
  ],
};

function sectionOf(tab: Tab): Section {
  return SECTIONS.find((s) => SECTION_TABS[s].some((t) => t.id === tab)) ?? "branches";
}

const iconProps = { width: 17, height: 17 };
const UNREAD_POLL_MS = 15000;

export default function AdminDashboard() {
  const [tab, setTab] = useTabParam(TABS, "orders");
  const [unread, setUnread] = useState(0);
  const toast = useToast();
  // Newest supplier <-> branch message already announced, so each one pops
  // up only once.
  const announcedPairMessage = useRef<number | null>(null);
  // Rejected price sheets for upcoming deliveries not yet followed up.
  const [rejectedSheets, setRejectedSheets] = useState(0);
  // Orders auto-submitted for branches that missed the cutoff, not yet reviewed.
  const [autoOrders, setAutoOrders] = useState(0);
  // A PO just issued from Supplier Orders, to open on the Purchase Orders tab.
  const [poFocus, setPoFocus] = useState<PoFocus | null>(null);

  // Every tab a user has opened this session stays mounted (just hidden)
  // instead of being torn down when they switch away — otherwise any
  // in-progress typing (draft quantities, prices, search filters) on the
  // tab they left would be lost the moment they came back to it, since a
  // fresh instance re-fetches from the server with nothing typed in yet.
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set([tab]));
  useEffect(() => {
    setVisited((prev) => (prev.has(tab) ? prev : new Set(prev).add(tab)));
  }, [tab]);

  // Reopening a section returns to the sub-tab last used in it.
  const section = sectionOf(tab);
  const lastTabInSection = useRef<Partial<Record<Section, Tab>>>({});
  lastTabInSection.current[section] = tab;
  function openSection(next: Section) {
    setTab(lastTabInSection.current[next] ?? SECTION_TABS[next][0].id);
  }

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
          if (cancelled) return;
          setUnread(r.count);
          const latest = r.latest_supplier_branch_id;
          if (latest !== null && latest !== announcedPairMessage.current) {
            announcedPairMessage.current = latest;
            const more = r.supplier_branch > 1 ? ` (${r.supplier_branch} unread)` : "";
            toast.show("info", `New supplier ↔ branch message: ${r.latest_supplier_branch}${more}. See Messages.`);
          }
        })
        .catch(() => {});
      fetchAdminAttentionCount()
        .then((r) => {
          if (!cancelled) setRejectedSheets(r.count);
        })
        .catch(() => {});
      fetchUnreviewedAutoOrders()
        .then((r) => {
          if (!cancelled) setAutoOrders(r.orders.length + r.missed.length);
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

  // Attention counts per page, rolled up onto the section in the sidebar.
  const tabBadges: Partial<Record<Tab, number>> = {
    orders: autoOrders,
    priceApprovals: rejectedSheets,
    messages: unread,
  };
  const sectionBadge = (sec: Section) => SECTION_TABS[sec].reduce((sum, t) => sum + (tabBadges[t.id] ?? 0), 0);

  const navItems: SidebarItem<Section>[] = [
    { id: "branches", label: "Branches", icon: <IconBranches {...iconProps} />, badge: sectionBadge("branches") },
    { id: "suppliers", label: "Suppliers", icon: <IconTruck {...iconProps} />, badge: sectionBadge("suppliers") },
    { id: "masterData", label: "Master Data Sheet", icon: <IconGrid {...iconProps} /> },
    { id: "messages", label: "Messages", icon: <IconChat {...iconProps} />, badge: sectionBadge("messages") },
    { id: "reports", label: "Reports", icon: <IconChart {...iconProps} /> },
    { id: "competitorPrices", label: "Competitor Prices", icon: <IconStore {...iconProps} /> },
    { id: "settings", label: "Settings", icon: <IconSettings {...iconProps} /> },
  ];

  const subTabs = SECTION_TABS[section];

  return (
    <DashboardShell
      title="Admin / Procurement Dashboard"
      subtitle="Central view across all branches and suppliers"
      navItems={navItems}
      activeNav={section}
      onNavChange={openSection}
      unreadCount={unread}
      onBellClick={() => setTab("messages")}
    >
      {subTabs.length > 1 && (
        <div className="-mx-1 mb-5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <div role="tablist" className="flex gap-1 bg-sage-100 rounded-full p-1 w-max mx-1">
            {subTabs.map((t) => {
              const active = t.id === tab;
              const badge = tabBadges[t.id];
              return (
                <button
                  key={t.id}
                  role="tab"
                  aria-selected={active}
                  onClick={() => setTab(t.id)}
                  className={`flex items-center gap-1.5 whitespace-nowrap text-sm rounded-full px-4 py-1.5 transition-colors duration-150 ${
                    active ? "bg-white text-crate-950 font-semibold shadow-sm" : "text-crate-800/60 hover:text-crate-800 font-medium"
                  }`}
                >
                  {t.label}
                  {!!badge && <CountBadge count={badge} />}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {keepAlive(
        "orders",
        <>
          <OrderMatrixView onAutoOrdersChanged={setAutoOrders} />
        </>
      )}
      {keepAlive(
        "orderHistory",
        <>
          <AdminOrderHistory />
        </>
      )}
      {keepAlive(
        "supplierOrders",
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-crate-800/60 mb-3">
            Give an order to a supplier
          </h2>
          <SupplierOrderBuilder
            onPurchaseOrderIssued={(po) => {
              setPoFocus({ deliveryDate: po.delivery_date, poId: po.id, nonce: Date.now() });
              setTab("purchaseOrders");
            }}
          />
        </>
      )}
      {keepAlive(
        "purchaseOrders",
        <>
          <AdminPurchaseOrders focus={poFocus} />
        </>
      )}
      {keepAlive(
        "supplierPrices",
        <>
          <SupplierPricesView />
        </>
      )}
      {keepAlive(
        "priceApprovals",
        <>
          <AdminPriceApprovals
            onChanged={() =>
              fetchAdminAttentionCount()
                .then((r) => setRejectedSheets(r.count))
                .catch(() => {})
            }
          />
        </>
      )}
      {keepAlive(
        "keellsPrices",
        <>
          <AdminKeellsPrices />
        </>
      )}
      {keepAlive(
        "marketPrices",
        <>
          <AdminMarketPrices />
        </>
      )}
      {keepAlive(
        "marketPriceHistory",
        <>
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
        "productList",
        <>
          <AdminProductList />
        </>
      )}
      {keepAlive(
        "promotions",
        <>
          <AdminPromotions />
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
      {keepAlive("supplierPriceHistory", <AdminSupplierPriceHistory />)}
      {keepAlive("reports", <ReportsView />)}
      {keepAlive(
        "auditLog",
        <>
          <AdminAuditLog />
        </>
      )}
      {keepAlive("users", <AdminUsers />)}
      {keepAlive("settings", <AdminSettings />)}
      {keepAlive("account", <AdminAccount />)}
    </DashboardShell>
  );
}
