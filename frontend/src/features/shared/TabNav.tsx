import { ReactNode } from "react";

export type TabItem<T extends string> = {
  id: T;
  label: string;
  icon: ReactNode;
  badge?: number;
};

export default function TabNav<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="inline-flex flex-wrap items-center gap-1 bg-sage-100 rounded-full p-1 mb-6">
      {tabs.map((t) => {
        const isActive = active === t.id;
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            className={`flex items-center gap-1.5 text-sm px-4 py-1.5 rounded-full transition-all duration-150 ${
              isActive
                ? "bg-white text-crate-800 font-semibold shadow-sm"
                : "text-crate-800/55 hover:text-crate-800 font-medium"
            }`}
          >
            <span className={isActive ? "text-crate-700" : "text-crate-800/35"}>{t.icon}</span>
            {t.label}
            {!!t.badge && (
              <span className="inline-flex items-center justify-center min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-tomato-500 text-white text-[10px] font-bold leading-none">
                {t.badge > 99 ? "99+" : t.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
