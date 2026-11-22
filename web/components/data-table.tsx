"use client";

import { Banner, Button, Empty, Skeleton } from "@/components/ui";
import { clsx } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";

export type Column<T> = {
  id: string;
  header: string;
  className?: string;
  cell: (row: T) => ReactNode;
};

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  pageSize = 8,
  pending = false,
  error = null,
  emptyTitle,
  emptyHint,
  onRow,
  activeKey,
  resetKey = "",
  renderExtra,
  total,
}: {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  pageSize?: number;
  pending?: boolean;
  error?: string | null;
  emptyTitle: string;
  emptyHint?: string;
  onRow?: (row: T) => void;
  activeKey?: string | null;
  resetKey?: string;
  renderExtra?: (row: T) => ReactNode;
  total?: number;
}) {
  const { t } = useI18n();
  const [page, setPage] = useState(0);
  const [seenKey, setSeenKey] = useState(resetKey);
  const [openKey, setOpenKey] = useState<string | null>(null);

  if (seenKey !== resetKey) {
    setSeenKey(resetKey);
    setPage(0);
    setOpenKey(null);
  }

  if (error) {
    return (
      <div className="p-5">
        <Banner>{error}</Banner>
      </div>
    );
  }

  if (pending) {
    return (
      <div className="space-y-3 p-5">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} className="h-10" />
        ))}
      </div>
    );
  }

  if (!rows.length) return <Empty title={emptyTitle} hint={emptyHint} />;

  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const safePage = Math.min(page, pages - 1);
  const start = safePage * pageSize;
  const visible = rows.slice(start, start + pageSize);
  const from = start + 1;
  const to = start + visible.length;
  const expandable = Boolean(renderExtra);

  function toggle(row: T) {
    const key = rowKey(row);
    if (onRow) onRow(row);
    if (!expandable) return;
    setOpenKey((current) => (current === key ? null : key));
  }

  return (
    <div>
      <div className="max-h-[32rem] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-white text-left text-xs font-mono uppercase tracking-[0.04em] text-ink-700/60">
            <tr>
              {expandable ? <th className="w-10 px-3 py-3" /> : null}
              {columns.map((column) => (
                <th key={column.id} className={clsx("px-4 py-3 font-semibold", column.className)}>
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const key = rowKey(row);
              const active = activeKey === key;
              const open = openKey === key;
              return (
                <FragmentRow key={key}>
                  <tr
                    onClick={onRow || expandable ? () => toggle(row) : undefined}
                    className={clsx(
                      "border-t border-paper-100",
                      (onRow || expandable) && "cursor-pointer",
                      active || open ? "bg-brand-100" : "hover:bg-paper-50",
                    )}
                  >
                    {expandable ? (
                      <td className="px-3 py-3 text-ink-700/50">
                        <ChevronDown size={16} className={clsx("transition", open && "rotate-180")} />
                      </td>
                    ) : null}
                    {columns.map((column) => (
                      <td key={column.id} className={clsx("px-4 py-3 align-middle", column.className)}>
                        {column.cell(row)}
                      </td>
                    ))}
                  </tr>
                  {open && renderExtra ? (
                    <tr className="border-t border-paper-100 bg-paper-50">
                      <td colSpan={columns.length + 1} className="px-5 py-4">
                        {renderExtra(row)}
                      </td>
                    </tr>
                  ) : null}
                </FragmentRow>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-paper-100 px-5 py-3 text-sm text-ink-700/70">
        <p>
          {t("table.range", { from, to, count: rows.length })}
          {total != null && total > rows.length ? t("table.truncated", { total, count: rows.length }) : ""}
        </p>
        <div className="flex gap-2">
          <Button type="button" variant="outline" className="px-3 py-1.5" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
            {t("table.prev")}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="px-3 py-1.5"
            disabled={safePage >= pages - 1}
            onClick={() => setPage(safePage + 1)}
          >
            {t("table.next")}
          </Button>
        </div>
      </div>
    </div>
  );
}

function FragmentRow({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
