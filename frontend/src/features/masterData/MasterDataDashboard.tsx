import { useAuth } from "../auth/AuthContext";
import DashboardShell from "../shared/DashboardShell";
import { IconGrid } from "../shared/Icons";
import { SidebarItem } from "../shared/Sidebar";
import MasterDataSheetView from "./MasterDataSheetView";

type Tab = "sheet";

const navItems: SidebarItem<Tab>[] = [
  { id: "sheet", label: "Master Data Sheet", icon: <IconGrid width={17} height={17} /> },
];

/** Head Office Master Data Team — only the sheet Admin sends them. */
export default function MasterDataDashboard() {
  const { user } = useAuth();
  return (
    <DashboardShell
      title="Master Data Team"
      subtitle={user ? `Signed in as ${user.username}` : "Master Data Team"}
      navItems={navItems}
      activeNav="sheet"
      onNavChange={() => {}}
    >
      <MasterDataSheetView />
    </DashboardShell>
  );
}
