"use client";
import { useState } from "react";
import { money, when } from "@/lib/format";
import type { Basket } from "@/lib/types";

export function BasketPanel({ b, busy, onApply, onSplit, onReview, onAddToCarts }: {
  b: Basket | null; busy: boolean; onApply: (i: number) => void; onSplit: (n: number) => void; onReview: () => void;
  onAddToCarts?: () => void;
}) {
  if (!b) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center text-zinc-500">
        <div className="text-4xl">🧺</div>
        <p className="font-medium text-zinc-700 dark:text-zinc-300">Your basket will build itself here</p>
        <p className="text-sm">Tell AgentKart what you&apos;re planning — by voice or text.</p>
      </div>
    );
  }
  const cur = b.currency;
  const fees = Object.values(b.fees).reduce<number>((a, f) => a + (f ?? 0), 0);
  const items = b.total_minor - fees;
  const scale = Math.max(b.budget_minor, b.total_minor);
  const pct = (b.total_minor / b.budget_minor) * 100;
  const tone = pct > 100 ? "bg-red-500" : pct >= 85 ? "bg-amber-500" : "bg-emerald-500";
  const stores = [...new Set(b.lines.map((l) => l.store_id))];
  const left = b.budget_minor - b.total_minor;

  const real = b.mode === "real";
  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className={`rounded-full px-2.5 py-1 font-medium ${real ? "bg-sky-100 text-sky-800" : "bg-violet-100 text-violet-800"}`}>
          {real ? "Real US stores · UCP · USD" : "Demo stores · UCP · INR"}
        </span>
        {real && <span className="text-zinc-500">carts only — AgentKart never orders or pays on real stores</span>}
        {!real && b.address && <span className="text-zinc-500">📍 Delivering to {b.address}</span>}
      </div>
      <section className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
        <div className="flex items-baseline justify-between">
          <div className="text-2xl font-semibold tabular-nums">{money(b.total_minor, cur)}</div>
          <div className="text-sm text-zinc-500">of {money(b.budget_minor, cur)} budget</div>
        </div>
        <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
          <div className={`${tone}`} style={{ width: `${(items / scale) * 100}%` }} title="Items" />
          <div className="bg-sky-500" style={{ width: `${(fees / scale) * 100}%` }} title="Delivery" />
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
          <span><i className={`mr-1 inline-block h-2 w-2 rounded-full ${tone}`} />Items {money(items, cur)}</span>
          <span><i className="mr-1 inline-block h-2 w-2 rounded-full bg-sky-500" />Delivery {money(fees, cur)}</span>
          <span className={left < 0 ? "font-medium text-red-600" : ""}>{left >= 0 ? `${money(left, cur)} left` : `${money(-left, cur)} over budget`}</span>
          {b.estimate && <span className="rounded bg-amber-100 px-1.5 text-amber-800">estimate</span>}
        </div>
        {b.insight && (
          <div className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
            ✂️ Using {b.insight.optimal_stores} stores instead of {b.insight.naive_stores} saved {money(b.insight.saving_minor, cur)}.
          </div>
        )}
      </section>

      {stores.map((sid) => {
        const lines = b.lines.filter((l) => l.store_id === sid);
        const fee = b.fees[sid];
        return (
          <section key={sid} className="rounded-xl border border-zinc-200 dark:border-zinc-800">
            <header className="flex items-center justify-between border-b border-zinc-200 px-4 py-2 dark:border-zinc-800">
              <h3 className="font-medium">{lines[0].store_name}</h3>
              <span className="rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                delivery {fee === 0 ? "free" : fee == null ? "at checkout" : money(fee, cur)}
              </span>
            </header>
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {lines.map((l) => (
                <li key={l.title + l.category} className="flex items-start justify-between gap-3 px-4 py-2.5">
                  {l.image_url && /* eslint-disable-next-line @next/next/no-img-element */ <img src={l.image_url} alt="" className="h-12 w-12 shrink-0 rounded-lg object-cover" />}
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm">{l.url ? <a href={l.url} target="_blank" rel="noreferrer" className="hover:underline">{l.title}</a> : l.title} <span className="text-zinc-400">× {l.packs}</span></div>
                    <div className="text-xs text-zinc-500">{l.rule}</div>
                    <span className={`mt-1 inline-block rounded px-1.5 text-[11px] ${l.eta ? (l.on_time ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800") : "bg-zinc-100 text-zinc-600"}`}>
                      {l.eta ? `arrives ${when(l.eta)}` : "at checkout"}
                    </span>
                  </div>
                  <div className="text-sm tabular-nums">{money(l.line_total_minor, cur)}</div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      {(b.excluded.length > 0 || b.late_notes.length > 0) && (
        <details className="rounded-xl border border-zinc-200 px-4 py-2 text-sm dark:border-zinc-800">
          <summary className="cursor-pointer font-medium">Excluded ({b.excluded.length})</summary>
          <ul className="mt-2 space-y-1 text-zinc-600 dark:text-zinc-400">
            {b.late_notes.map((n, i) => (
              <li key={i}>⏰ {n.store_name} {n.category.replace("_", " ")} is {money(n.cheaper_by_minor, cur)} cheaper but arrives {when(n.eta)}, after your deadline.</li>
            ))}
            {b.excluded.filter((e) => e.reason !== "late").map((e, i) => (
              <li key={`o${i}`}>🚫 {e.store_name}: {e.title} ({e.reason.replace("_", " ")})</li>
            ))}
          </ul>
        </details>
      )}

      {b.options.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-sm font-medium text-red-700 dark:text-red-400">Over budget — pick a trade-off</h3>
          {b.options.map((o) => (
            <div key={o.index} className="flex items-center justify-between gap-3 rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
              <div className="text-sm">
                <div className="font-medium">{o.title}</div>
                <div className="text-zinc-500">saves {money(-o.delta_minor, cur)} → {money(o.new_total_minor, cur)} {o.within_budget ? "✅ within budget" : "(still over)"}</div>
              </div>
              <button disabled={busy} onClick={() => onApply(o.index)}
                className="rounded-lg bg-zinc-900 px-3 py-1.5 text-sm text-white hover:bg-zinc-700 disabled:opacity-50 dark:bg-white dark:text-black">Apply</button>
            </div>
          ))}
        </section>
      )}

      <Split b={b} onSplit={onSplit} />

      {real && b.real_carts.length > 0 && <RealCarts carts={b.real_carts} />}
      <button disabled={busy || !b.feasible} onClick={real ? onAddToCarts : onReview}
        className="w-full rounded-xl bg-emerald-600 py-3 font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40">
        {!b.feasible ? "Fix the budget to continue" : real ? (b.real_carts.length ? "Refresh carts" : "Add to carts at each store") : "Review & approve order"}
      </button>
    </div>
  );
}

function Split({ b, onSplit }: { b: Basket; onSplit: (n: number) => void }) {
  const [copied, setCopied] = useState(false);
  const n = b.payers;
  const msg = b.shares_minor
    ? `Hey! We're chipping in for the party order (${money(b.total_minor, b.currency)} total). Your share: ${money(Math.max(...b.shares_minor), b.currency)}.`
    : "";
  return (
    <section className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Split between friends</span>
        <div className="flex items-center gap-2">
          <button className="h-7 w-7 rounded-full border text-lg leading-none disabled:opacity-40" disabled={n <= 1} onClick={() => onSplit(n - 1)}>−</button>
          <span className="w-6 text-center tabular-nums">{n}</span>
          <button className="h-7 w-7 rounded-full border text-lg leading-none" onClick={() => onSplit(n + 1)}>+</button>
        </div>
      </div>
      {b.shares_minor && (
        <div className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
          {b.shares_minor.map((s, i) => <span key={i} className="mr-2 inline-block rounded bg-zinc-100 px-2 py-0.5 tabular-nums dark:bg-zinc-800">{money(s, b.currency)}</span>)}
          <div className="mt-1 text-xs text-zinc-500">Shares add up to exactly {money(b.total_minor, b.currency)}.</div>
          <button className="mt-2 text-xs underline" onClick={() => { navigator.clipboard?.writeText(msg); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>
            {copied ? "Copied!" : "Copy message for friends"}
          </button>
        </div>
      )}
    </section>
  );
}

function RealCarts({ carts }: { carts: NonNullable<Basket["real_carts"]> }) {
  return (
    <section className="space-y-2 rounded-xl border border-sky-200 bg-sky-50/60 p-3 dark:border-sky-900 dark:bg-sky-950/30">
      <h3 className="text-sm font-medium">Your carts are ready — nothing has been ordered</h3>
      {carts.map((c) => (
        <div key={c.store_id} className="flex items-center justify-between gap-3 rounded-lg bg-white p-3 dark:bg-zinc-900">
          <div className="text-sm">
            <div className="font-medium">{c.store_name ?? c.store_domain}</div>
            <div className="text-xs text-zinc-500">{c.lines.length} item{c.lines.length > 1 ? "s" : ""} · subtotal {money(c.subtotal_minor, "USD")} + shipping &amp; tax at checkout
              {c.degraded.length > 0 && <span className="ml-1 rounded bg-amber-100 px-1 text-amber-800">{c.degraded[0].replace(/_/g, " ")}</span>}</div>
          </div>
          {c.handoff_url
            ? <a href={c.handoff_url} target="_blank" rel="noreferrer" className="shrink-0 rounded-lg bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-500">Open cart ↗</a>
            : <a href={`https://${c.store_domain}`} target="_blank" rel="noreferrer" className="shrink-0 rounded-lg border px-3 py-1.5 text-sm">Open store ↗</a>}
        </div>
      ))}
      <p className="text-xs text-zinc-500">You review and pay on each store&apos;s own site. AgentKart never enters payment details.</p>
    </section>
  );
}
