import { createPortal } from "react-dom";
import { SidebarItem } from "./Sidebar";
import { CountBadge } from "./ui/Badge";

export default function MobileNavDrawer<T extends string>({
  open,
  onClose,
  items,
  active,
  onChange,
  brandTitle,
}: {
  open: boolean;
  onClose: () => void;
  items: SidebarItem<T>[];
  active: T;
  onChange: (id: T) => void;
  brandTitle: string;
}) {
  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 md:hidden">
      <div className="absolute inset-0 bg-crate-950/40" onClick={onClose} aria-hidden="true" />
      <div className="relative w-64 max-w-[80vw] h-full bg-white shadow-modal flex flex-col animate-fade-up" style={{ animationDuration: "0.2s" }}>
        <div className="flex flex-col items-center justify-center gap-1 h-16 shrink-0 border-b border-sage-100 px-3">
          <img
            src="/images/spar-logo.svg"
            alt="SPAR"
            className="h-7 w-auto object-contain"
          />
          <span className="font-display font-bold text-sm text-crate-950 truncate">{brandTitle}</span>
        </div>
        <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
          {items.map((item) => {
            const isActive = item.id === active;
            return (
              <button
                key={item.id}
                onClick={() => {
                  onChange(item.id);
                  onClose();
                }}
                className={`w-full flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm transition-colors duration-150 ${
                  isActive
                    ? "bg-tomato-500/10 text-tomato-600 font-semibold"
                    : "text-crate-800/60 hover:bg-sage-50 hover:text-crate-800 font-medium"
                }`}
              >
                <span className={isActive ? "text-tomato-600" : "text-crate-800/40"}>{item.icon}</span>
                <span className="truncate flex-1 text-left">{item.label}</span>
                {!!item.badge && <CountBadge count={item.badge} />}
              </button>
            );
          })}
        </nav>
      </div>
    </div>,
    document.body
  );
}
