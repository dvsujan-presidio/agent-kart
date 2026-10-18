"use client";
import { ApprovalModal } from "@/components/ApprovalModal";
import { BasketPanel } from "@/components/BasketPanel";
import { OrderTracker } from "@/components/OrderTracker";
import { useAgentKart } from "@/lib/useAgentKart";

/** Deep-linkable review screen (Teams links here). Approval happens only here or by voice, never in Teams. */
export function ReviewClient({ sid }: { sid: string }) {
  const ak = useAgentKart(sid);
  return (
    <div className="mx-auto max-w-2xl">
      <header className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <h1 className="text-lg font-semibold">Review your AgentKart order</h1>
        <p className="text-xs text-zinc-500">Session {sid}. Nothing is ordered until you approve.</p>
      </header>
      {ak.error && <div className="bg-red-50 px-4 py-2 text-sm text-red-800">{ak.error}</div>}
      <BasketPanel b={ak.basket} busy={ak.busy} onApply={ak.applyOption} onSplit={ak.split} onReview={ak.askApproval} onAddToCarts={ak.addToCarts} />
      <OrderTracker orders={ak.orders} fallback={ak.fallback} demo={false} onDelay={() => {}} onDismiss={() => ak.setFallback(null)} />
      {ak.approval && <ApprovalModal a={ak.approval} busy={ak.busy} onApprove={ak.approve} onCancel={ak.dismissApproval} />}
    </div>
  );
}
