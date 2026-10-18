"use client";
import { useEffect, useRef, useState } from "react";
import type { ChatMsg } from "@/lib/types";

const SUGGESTIONS = [
  "Help me shop for a birthday party for 10 people tomorrow evening, under ₹3,000. I already have plates.",
];

export function Chat({ messages, busy, onSend }: { messages: ChatMsg[]; busy: boolean; onSend: (t: string) => void }) {
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);
  const submit = () => { const t = text.trim(); if (t && !busy) { onSend(t); setText(""); } };
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
              m.role === "user" ? "bg-zinc-900 text-white dark:bg-white dark:text-black"
                : m.fallback ? "border border-amber-300 bg-amber-50 text-amber-950 dark:bg-amber-950 dark:text-amber-100"
                : "bg-zinc-100 dark:bg-zinc-800"}`}>
              {m.channel === "voice" && m.role === "user" && <span className="mr-1">🎙️</span>}{m.text}
            </div>
          </div>
        ))}
        {!messages.some((m) => m.role === "user") && (
          <div className="mx-auto mt-2 max-w-md space-y-3 rounded-2xl border border-emerald-200 bg-emerald-50/60 p-4 text-center dark:border-emerald-900 dark:bg-emerald-950/40">
            <button onClick={() => window.dispatchEvent(new Event("agentkart:voice"))}
              className="mx-auto flex items-center gap-2 rounded-full bg-emerald-600 px-5 py-3 text-base font-medium text-white shadow hover:bg-emerald-500">
              🎙️ Talk to AgentKart
            </button>
            <p className="text-xs text-zinc-600 dark:text-zinc-300">Just say what you need. I&apos;ll ask a couple of questions, show the basket on the right, and read the order back before anything is placed.</p>
            <div className="text-xs text-zinc-500">or type it:</div>
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => onSend(s)} className="block w-full rounded-xl border border-dashed border-zinc-300 px-3 py-2 text-left text-sm hover:bg-white dark:border-zinc-700 dark:hover:bg-zinc-900">“{s}”</button>
            ))}
          </div>
        )}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <span className="inline-flex gap-1"><i className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400" /><i className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:150ms]" /><i className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:300ms]" /></span>
            Understanding · searching stores over UCP · optimizing…
          </div>
        )}
        <div ref={end} />
      </div>
      <div className="flex gap-2 border-t border-zinc-200 p-3 dark:border-zinc-800">
        <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Type, or tap the mic to talk…" className="flex-1 rounded-xl border border-zinc-300 bg-transparent px-3 py-2 text-sm outline-none focus:border-zinc-500 dark:border-zinc-700" />
        <button onClick={submit} disabled={busy || !text.trim()} className="rounded-xl bg-zinc-900 px-4 text-sm text-white disabled:opacity-40 dark:bg-white dark:text-black">Send</button>
      </div>
    </div>
  );
}
