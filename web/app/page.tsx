"use client";
import dynamic from "next/dynamic";
import { ApprovalModal } from "@/components/ApprovalModal";
import { BasketPanel } from "@/components/BasketPanel";
import { Chat } from "@/components/Chat";
import { OrderTracker } from "@/components/OrderTracker";
import { useAgentKart } from "@/lib/useAgentKart";

const VoicePanel = dynamic(() => import("@/components/VoicePanel").then((m) => m.VoicePanel), { ssr: false });

export default function Home() {
  const ak = useAgentKart();
  return (
    <div className="flex h-dvh flex-col">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <div>
          <h1 className="text-lg font-semibold">AgentKart</h1>
          <p className="text-xs text-zinc-500">Get a job done, not just a product · UCP stores · you approve every order</p>
        </div>
        <div className="flex items-center gap-3">
          {ak.approvedNote && <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs text-emerald-800">{ak.approvedNote}</span>}
          <VoicePanel sid={ak.sid} />
        </div>
      </header>
      {ak.error && (
        <div className="flex items-center justify-between bg-red-50 px-4 py-2 text-sm text-red-800">
          <span>{ak.error}</span><button className="underline" onClick={() => ak.setError(null)}>dismiss</button>
        </div>
      )}
      <main className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <section className="min-h-0 border-b border-zinc-200 md:border-b-0 md:border-r dark:border-zinc-800"><Chat messages={ak.messages} busy={ak.busy} onSend={ak.send} /></section>
        <section className="min-h-0 overflow-y-auto">
          <BasketPanel b={ak.basket} busy={ak.busy} onApply={ak.applyOption} onSplit={ak.split} onReview={ak.askApproval} onAddToCarts={ak.addToCarts} />
          <OrderTracker orders={ak.orders} fallback={ak.fallback} demo onDelay={ak.delay} onDismiss={() => ak.setFallback(null)} />
        </section>
      </main>
      {ak.approval && <ApprovalModal a={ak.approval} busy={ak.busy} onApprove={ak.approve} onCancel={ak.dismissApproval} />}
    </div>
  );
}
