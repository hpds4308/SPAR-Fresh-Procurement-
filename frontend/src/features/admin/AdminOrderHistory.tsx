import { useState } from "react";
import BranchOrderHistory from "./BranchOrderHistory";
import SupplierOrderHistory from "./SupplierOrderHistory";

type View = "branches" | "suppliers";

export default function AdminOrderHistory() {
  const [view, setView] = useState<View>("branches");

  return (
    <div className="space-y-4">
      <div className="flex gap-1 bg-sage-100 rounded-full p-0.5 w-fit">
        {(["branches", "suppliers"] as View[]).map((v) => (
          <button
            key={v}
            onClick={() => setView(v)}
            className={`text-sm font-semibold rounded-full px-5 py-1.5 transition-colors duration-150 ${
              view === v ? "bg-white text-crate-950 shadow-sm" : "text-crate-800/50 hover:text-crate-800"
            }`}
          >
            {v === "branches" ? "Branch wise" : "Supplier wise"}
          </button>
        ))}
      </div>

      {view === "branches" ? <BranchOrderHistory /> : <SupplierOrderHistory />}
    </div>
  );
}
