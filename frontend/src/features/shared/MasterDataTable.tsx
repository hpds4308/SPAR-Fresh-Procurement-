import { ReactNode } from "react";
import { MasterDataRow, MasterDataSupplierColumn } from "../../api/masterData";
import { CategoryBadge } from "./ui/CategoryBadge";
import { ProductPromotion } from "./ui/PromotionBadge";

function shortDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

const dash = <span className="text-crate-800/20">—</span>;

/**
 * The Master Data Sheet table — one layout for Admin (editable Target GP%
 * and Selling Price, passed in as render functions) and the Master Data
 * Team (read-only, plus the price branches currently see).
 */
export default function MasterDataTable({
  suppliers,
  rows,
  renderTargetGp,
  renderSellingPrice,
  showPublished = false,
}: {
  suppliers: MasterDataSupplierColumn[];
  rows: MasterDataRow[];
  renderTargetGp?: (row: MasterDataRow) => ReactNode;
  renderSellingPrice?: (row: MasterDataRow) => ReactNode;
  showPublished?: boolean;
}) {
  return (
    <div className="bg-white rounded-2xl shadow-card border border-sage-100 overflow-x-auto">
      <table className="text-sm border-collapse min-w-max">
        <thead>
          <tr className="bg-sage-50 text-crate-800/50 text-xs uppercase tracking-wide">
            <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 0, width: 90, minWidth: 90 }}>
              Category
            </th>
            <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 90, width: 90, minWidth: 90 }}>
              Code
            </th>
            <th className="text-left px-3 py-2.5 sticky z-20 bg-sage-50" style={{ left: 180, width: 90, minWidth: 90 }}>
              POS Code
            </th>
            <th
              className="text-left px-3 py-2.5 sticky z-20 bg-sage-50 shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
              style={{ left: 270, width: 190, minWidth: 190 }}
            >
              Description
            </th>
            <th className="text-right px-3 py-2.5 whitespace-nowrap">Target GP%</th>
            <th className="text-right px-3 py-2.5 whitespace-nowrap">Selling Price</th>
            {showPublished && (
              <th className="text-right px-3 py-2.5 whitespace-nowrap">
                Published
                <div className="text-[9px] font-normal normal-case text-crate-800/35">What branches see</div>
              </th>
            )}
            <th className="text-right px-3 py-2.5 whitespace-nowrap">GP%</th>
            <th className="text-right px-3 py-2.5 whitespace-nowrap bg-green-100/60">
              Keells Price
              <div className="text-[9px] font-normal normal-case text-crate-800/35">Latest entered</div>
            </th>
            <th className="text-right px-3 py-2.5 whitespace-nowrap">
              Cost Price
              <div className="text-[9px] font-normal normal-case text-crate-800/35">Highest submitted price</div>
            </th>
            {suppliers.map((s) => (
              <th key={s.supplier_id} className="text-right px-3 py-2.5 whitespace-nowrap bg-mango-500/10">
                {s.supplier_name}
                <div className="text-[9px] font-normal normal-case text-crate-800/35">Adjusted CP</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-sage-100">
          {rows.map((row) => {
            const gpBelow = row.computed_gp_percent !== null && row.computed_gp_percent < row.target_gp_percent;
            const toPublish =
              row.selling_price !== null && row.published_selling_price !== row.selling_price;
            return (
              <tr key={row.product_id} className="hover:bg-sage-50/50 transition-colors duration-100">
                <td className="px-3 py-2 sticky z-10 bg-white" style={{ left: 0, width: 90 }}>
                  <CategoryBadge name={row.category_name} />
                </td>
                <td className="px-3 py-2 text-crate-800/40 sticky z-10 bg-white" style={{ left: 90, width: 90 }}>
                  {row.product_code}
                </td>
                <td className="px-3 py-2 text-crate-800/60 sticky z-10 bg-white" style={{ left: 180, width: 90 }}>
                  {row.pos_code ?? dash}
                </td>
                <td
                  className="px-3 py-2 text-crate-950 sticky z-10 bg-white shadow-[2px_0_2px_-1px_rgba(21,56,38,0.08)]"
                  style={{ left: 270, width: 190 }}
                >
                  {row.description}
                  <ProductPromotion productId={row.product_id} className="ml-1.5" />
                </td>
                {renderTargetGp ? (
                  <td className="px-2 py-1.5 text-right">{renderTargetGp(row)}</td>
                ) : (
                  <td className="px-3 py-2 text-right text-crate-800/70 whitespace-nowrap">
                    {(row.target_gp_percent * 100).toFixed(1)}%
                  </td>
                )}
                {renderSellingPrice ? (
                  <td className="px-2 py-1.5">{renderSellingPrice(row)}</td>
                ) : (
                  <td className="px-3 py-2 text-right whitespace-nowrap font-semibold text-crate-950">
                    {row.selling_price !== null ? `Rs. ${row.selling_price.toFixed(2)}` : dash}
                  </td>
                )}
                {showPublished && (
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    {row.published_selling_price !== null ? (
                      <span className={toPublish ? "text-[#8A5A0D]" : "text-crate-700"}>
                        Rs. {row.published_selling_price.toFixed(2)}
                      </span>
                    ) : (
                      dash
                    )}
                    {toPublish && (
                      <div className="text-[9px] text-[#8A5A0D] leading-none mt-0.5">Not published yet</div>
                    )}
                  </td>
                )}
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  {row.computed_gp_percent !== null ? (
                    <span className={`font-semibold ${gpBelow ? "text-tomato-600" : "text-crate-700"}`}>
                      {(row.computed_gp_percent * 100).toFixed(1)}%
                    </span>
                  ) : (
                    dash
                  )}
                </td>
                <td className="px-3 py-2 text-right text-crate-800/70 whitespace-nowrap bg-green-100/30">
                  {row.keells_price !== null ? (
                    <div className="flex flex-col items-end">
                      <span>Rs. {row.keells_price.toFixed(2)}</span>
                      {row.keells_price_date && (
                        <span className="text-[9px] text-crate-800/40 leading-none mt-0.5">
                          {shortDate(row.keells_price_date)}
                        </span>
                      )}
                    </div>
                  ) : (
                    dash
                  )}
                </td>
                <td className="px-3 py-2 text-right text-crate-800/70 whitespace-nowrap">
                  {row.cost_price !== null ? (
                    <div className="flex flex-col items-end">
                      <span>Rs. {row.cost_price.toFixed(2)}</span>
                      {row.cost_price_supplier_name && (
                        <span className="text-[9px] text-crate-800/40 leading-none mt-0.5">
                          {row.cost_price_supplier_name}
                          {row.cost_price_date ? ` · ${shortDate(row.cost_price_date)}` : ""}
                        </span>
                      )}
                    </div>
                  ) : (
                    dash
                  )}
                </td>
                {suppliers.map((s) => {
                  const price = row.supplier_prices[s.supplier_id];
                  return (
                    <td key={s.supplier_id} className="px-3 py-2 text-right text-crate-800/70 bg-mango-500/5">
                      {price !== null && price !== undefined ? price.toFixed(2) : dash}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
