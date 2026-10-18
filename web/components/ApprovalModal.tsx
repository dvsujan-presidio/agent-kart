"use client";
import { useEffect, useState } from "react";
import { money, when } from "@/lib/format";
import type { ApprovalReq } from "@/lib/types";

export function ApprovalModal({ a, busy, onApprove, onCancel }: { a: ApprovalReq; busy: boolean; onApprove: () => void; onCancel: () => void }) {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    const tick = () => setLeft(Math.max(0, Math.round((new Date(a.expires_at).getTime() - Date.now()) / 1000)));
    tick(); const t = setInterval(tick, 500); return () => clearInterval(t);
  }, [a.expires_at]);
  const b = a.basket;
  const stores = b ? [...new Set(b.lines.map((l) => l.store_name))] : [];
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl dark:bg-zinc-900">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold">{a.kind === "backup" ? "Approve backup order" : "Approve this exact order"}</h2>
            <p className="text-xs text-zinc-500">Locked to basket <code>{b?.hash.slice(0, 8)}</code> · expires in {left}s. Say “yes, place the order” or tap Approve.</p>
          </div>
        </div>
        <p className="mt-3 rounded-lg bg-zinc-100 px-3 py-2 text-sm dark:bg-zinc-800">🔊 {a.readback}</p>
        {b && (
          <div className="mt-3 space-y-3">
            {stores.map((s) => (
              <div key={s} className="rounded-lg border border-zinc-200 dark:border-zinc-700">
                <div className="flex justify-between border-b border-zinc-200 px-3 py-1.5 text-sm font-medium dark:border-zinc-700">
                  <span>{s}</span><span className="text-xs text-zinc-500">delivery {money(b.fees[b.lines.find((l) => l.store_name === s)!.store_id] ?? null, b.currency)}</span>
                </div>
                {b.lines.filter((l) => l.store_name === s).map((l) => (
                  <div key={l.title} className="flex justify-between gap-2 px-3 py-1 text-sm">
                    <span className="truncate">{l.title} × {l.packs} <span className="text-xs text-zinc-400">({when(l.eta)})</span></span>
                    <span className="tabular-nums">{money(l.line_total_minor, b.currency)}</span>
                  </div>
                ))}
              </div>
            ))}
            <div className="flex justify-between text-base font-semibold"><span>Total</span><span className="tabular-nums">{money(b.total_minor, b.currency)}</span></div>
          </div>
        )}
        <div className="mt-4 flex gap-2">
          <button onClick={onCancel} className="flex-1 rounded-xl border border-zinc-300 py-2.5 dark:border-zinc-700">Not yet</button>
          <button onClick={onApprove} disabled={busy || left === 0} className="flex-1 rounded-xl bg-emerald-600 py-2.5 font-medium text-white hover:bg-emerald-500 disabled:opacity-40">
            {busy ? "Placing…" : "Approve & place order"}
          </button>
        </div>
      </div>
    </div>
  );
}
