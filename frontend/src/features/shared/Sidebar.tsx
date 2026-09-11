import { ReactNode } from "react";
import { IconChevronLeft, IconChevronRight } from "./Icons";
import { CountBadge } from "./ui/Badge";

export type SidebarItem<T extends string> = {
  id: T;
  label: string;
  icon: ReactNode;
  badge?: number;
};

export default function Sidebar<T extends string>({
  items,
  active,
  onChange,
  collapsed,
  onToggleCollapsed,
}: {
  items: SidebarItem<T>[];
  active: T;
  onChange: (id: T) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  return (
    <aside
      className={`hidden md:flex flex-col shrink-0 h-screen bg-white border-r border-sage-200 transition-all duration-200 ${
        collapsed ? "w-16" : "w-56"
      }`}
    >
      <div className={`flex items-center justify-center h-16 shrink-0 border-b border-sage-100 ${collapsed ? "px-2" : "px-4"}`}>
        <img
          src={collapsed ? "/images/spar-icon.svg" : "/images/spar-logo.svg"}
          alt="SPAR"
          className={`w-auto object-contain ${collapsed ? "h-8" : "h-7"}`}
        />
      </div>

      {/* min-h-0 lets this nav shrink inside the flex column so it scrolls
          independently — the logo and collapse toggle stay pinned. */}
      <nav className="flex-1 min-h-0 py-3 px-2 space-y-0.5 overflow-y-auto">
        {items.map((item) => {
          const isActive = item.id === active;
          return (
            <button
              key={item.id}
              onClick={() => onChange(item.id)}
              title={collapsed ? item.label : undefined}
              className={`w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition-colors duration-150 relative ${
                collapsed ? "justify-center" : ""
              } ${
                isActive
                  ? "bg-tomato-500/10 text-tomato-600 font-semibold"
                  : "text-crate-800/60 hover:bg-sage-50 hover:text-crate-800 font-medium"
              }`}
            >
              <span className={isActive ? "text-tomato-600" : "text-crate-800/40"}>{item.icon}</span>
              {!collapsed && <span className="truncate flex-1 text-left">{item.label}</span>}
              {!!item.badge && (collapsed ? (
                <span className="absolute top-1.5 right-1.5">
                  <CountBadge count={item.badge} />
                </span>
              ) : (
                <CountBadge count={item.badge} />
              ))}
            </button>
          );
        })}
      </nav>

      <button
        onClick={onToggleCollapsed}
        className="flex items-center justify-center gap-2 h-11 shrink-0 border-t border-sage-100 text-crate-800/40 hover:text-crate-700 hover:bg-sage-50 transition-colors duration-150"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <IconChevronRight width={14} height={14} /> : <IconChevronLeft width={14} height={14} />}
      </button>
    </aside>
  );
}
