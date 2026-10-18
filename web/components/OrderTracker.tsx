"use client";
import { money, when } from "@/lib/format";
import type { Order } from "@/lib/types";

const STEPS = ["placed", "packed", "out_for_delivery", "delivered"];

export function OrderTracker({ orders, fallback, demo, onDelay, onDismiss }: {
  orders: Order[]; fallback: string | null; demo: boolean; onDelay: () => void; onDismiss: () => void;
}) {
  if (orders.length === 0) return null;
  return (
    <section className="space-y-2 p-4 pt-0">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Orders</h3>
        {demo && <button onClick={onDelay} className="rounded-lg border border-dashed border-zinc-400 px-2 py-1 text-xs text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800">⚡ Simulate cake delay (demo)</button>}
      </div>
      {fallback && (
        <div className="flex items-start justify-between gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:bg-amber-950 dark:text-amber-100">
          <span>⚠️ {fallback}</span><button className="text-xs underline" onClick={onDismiss}>dismiss</button>
        </div>
      )}
      {orders.map((o) => {
        const step = STEPS.indexOf(o.status);
        return (
          <div key={o.order_id} className={`rounded-xl border p-3 ${o.replaced ? "opacity-50" : ""} border-zinc-200 dark:border-zinc-800`}>
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{o.store_name}{o.kind === "backup" && " (backup, pickup)"}</span>
              <span className="tabular-nums">{money(o.total_minor)}</span>
            </div>
            <div className="text-xs text-zinc-500">{o.order_id} · {o.items.length} item{o.items.length > 1 ? "s" : ""} · eta {when(o.eta)}</div>
            {o.status === "delayed" ? (
              <div className="mt-2 rounded bg-red-100 px-2 py-1 text-xs font-medium text-red-800">Delayed — now arriving {when(o.eta)}</div>
            ) : (
              <div className="mt-2 flex gap-1">
                {STEPS.map((s, i) => <div key={s} title={s} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-emerald-500" : "bg-zinc-200 dark:bg-zinc-700"}`} />)}
              </div>
            )}
            <div className="mt-1 text-[11px] capitalize text-zinc-500">{o.replaced ? "replaced by backup" : o.status.replace(/_/g, " ")}</div>
          </div>
        );
      })}
    </section>
  );
}
