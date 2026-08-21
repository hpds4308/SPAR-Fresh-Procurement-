import { ReactNode } from "react";
import { IconCrate } from "./Icons";

export default function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
}) {
  return (
    <div className="bg-white rounded-2xl shadow-[0_10px_30px_-12px_rgba(21,56,38,0.15)] border border-sage-100 py-12 px-8 text-center">
      <div className="mx-auto mb-3.5 w-11 h-11 rounded-full bg-sage-100 flex items-center justify-center text-crate-700/50">
        {icon ?? <IconCrate width={20} height={20} />}
      </div>
      <p className="text-sm font-semibold text-crate-800/70">{title}</p>
      {description && <p className="text-xs text-crate-800/40 mt-1 max-w-sm mx-auto">{description}</p>}
    </div>
  );
}
