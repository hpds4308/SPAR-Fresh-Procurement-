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
    <div className="min-h-screen bg-gray-50 font-body flex">
      <Sidebar
        items={navItems}
        active={activeNav}
        onChange={onNavChange}
        collapsed={collapsed}
        onToggleCollapsed={toggleCollapsed}
        brandTitle="SPAR Procurement"
      />
      <MobileNavDrawer
        open={mobileNavOpen}
        onClose={() => setMobileNavOpen(false)}
        items={navItems}
        active={activeNav}
        onChange={onNavChange}
        brandTitle="SPAR Procurement"
      />

      <div className="flex-1 min-w-0 flex flex-col">
        <Header
          title={title}
          subtitle={subtitle}
          unreadCount={unreadCount}
          onBellClick={onBellClick}
          onMenuClick={() => setMobileNavOpen(true)}
        />
        <main className="flex-1 px-4 md:px-6 py-6 md:py-8 animate-fade-up max-w-6xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
