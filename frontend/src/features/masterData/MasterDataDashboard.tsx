import { useAuth } from "../auth/AuthContext";
import DashboardShell from "../shared/DashboardShell";
import { IconGrid, IconReceipt, IconTag } from "../shared/Icons";
import { SidebarItem } from "../shared/Sidebar";
import { FadeSwitch } from "../shared/ui/FadeSwitch";
import { useTabParam } from "../shared/useTabParam";
import CostPricesView from "./CostPricesView";
import MasterDataSheetView from "./MasterDataSheetView";
import SellingPricesView from "./SellingPricesView";

const TABS = ["sheet", "costPrices", "sellingPrices"] as const;
type Tab = (typeof TABS)[number];

const iconProps = { width: 17, height: 17 };

const navItems: SidebarItem<Tab>[] = [
  { id: "sheet", label: "Master Data Sheet", icon: <IconGrid {...iconProps} /> },
  { id: "costPrices", label: "Cost Prices", icon: <IconReceipt {...iconProps} /> },
  { id: "sellingPrices", label: "Selling Prices", icon: <IconTag {...iconProps} /> },
];

/** Head Office Master Data Team — only the sheet Admin sends them. */
export default function MasterDataDashboard() {
  const { user } = useAuth();
  const [tab, setTab] = useTabParam(TABS, "sheet");
  return (
    <DashboardShell
      title="Master Data Team"
      subtitle={user ? `Signed in as ${user.username}` : "Master Data Team"}
      navItems={navItems}
      activeNav={tab}
      onNavChange={setTab}
    >
      <FadeSwitch tabKey={tab}>
        {tab === "sheet" && <MasterDataSheetView />}
        {tab === "costPrices" && <CostPricesView />}
        {tab === "sellingPrices" && <SellingPricesView />}
      </FadeSwitch>
    </DashboardShell>
  );
}
