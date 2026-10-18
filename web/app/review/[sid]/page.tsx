import { Suspense } from "react";
import { ReviewClient } from "./ReviewClient";

async function Review({ params }: { params: Promise<{ sid: string }> }) {
  const { sid } = await params;
  return <ReviewClient sid={sid} />;
}

export default function ReviewPage({ params }: { params: Promise<{ sid: string }> }) {
  return (
    <Suspense fallback={<p className="p-6 text-sm text-zinc-500">Loading your order…</p>}>
      <Review params={params} />
    </Suspense>
  );
}
