import { ReactNode, useState } from "react";
import Sidebar, { SidebarItem } from "./Sidebar";
import MobileNavDrawer from "./MobileNavDrawer";
import Header from "./Header";

const COLLAPSE_STORAGE_KEY = "spar_sidebar_collapsed";

function getInitialCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export default function DashboardShell<T extends string>({
  title,
  subtitle,
  navItems,
  activeNav,
  onNavChange,
  unreadCount,
  onBellClick,
  children,
}: {
  title: string;
  subtitle: string;
  navItems: SidebarItem<T>[];
  activeNav: T;
  onNavChange: (id: T) => void;
  unreadCount?: number;
  onBellClick?: () => void;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(getInitialCollapsed);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? "1" : "0");
      } catch {
        // ignore — collapse state is a nicety, not critical
      }
      return next;
    });
  }

  return (
    // h-screen + overflow-hidden pins the app to the viewport so the page
    // itself never scrolls; the sidebar and the main column each get their
    // own scroll container below.
    <div className="h-screen overflow-hidden bg-gray-50 font-body flex">
      <Sidebar
        items={navItems}
        active={activeNav}
        onChange={onNavChange}
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
      />
      <MobileNavDrawer
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        items={navItems}
        active={activeNav}
        onChange={onNavChange}
      />

      <div className="flex-1 min-w-0 flex flex-col h-screen">
        <Header
          title={title}
          subtitle={subtitle}
          unreadCount={unreadCount}
          onBellClick={onBellClick}
          onMenuClick={() => setMobileNavOpen(true)}
        />
        {/* min-h-0 lets this flex child shrink so it — not the page — is the
            scroll container for page content. */}
        <main className="flex-1 min-h-0 overflow-y-auto">
          <div className="px-4 md:px-6 py-6 md:py-8 animate-fade-up max-w-6xl w-full mx-auto">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
