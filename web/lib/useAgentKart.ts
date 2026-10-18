/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { API, api } from "./api";
import type { ApprovalReq, Basket, ChatMsg, Order } from "./types";

export function useAgentKart(existingSid?: string) {
  const [sid, setSid] = useState<string | null>(existingSid ?? null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [basket, setBasket] = useState<Basket | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [approval, setApproval] = useState<ApprovalReq | null>(null);
  const [approvedNote, setApprovedNote] = useState<string | null>(null);
  const [fallback, setFallback] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    (async () => {
      try {
        const id = existingSid ?? (await api.newSession()).session_id;
        setSid(id);
      } catch (e) { setError(`Cannot reach the API at ${API}. Is it running? (${(e as Error).message})`); }
    })();
  }, [existingSid]);

  useEffect(() => {
    if (!sid) return;
    const es = new EventSource(`${API}/sessions/${sid}/events`);
    const on = (t: string, f: (d: any) => void) => es.addEventListener(t, (e) => f(JSON.parse((e as MessageEvent).data)));
    on("chat_message", (d) => setMessages((m) => [...m, { role: d.role, text: d.text, fallback: d.fallback, channel: d.channel }]));
    on("basket_updated", (d) => setBasket(d));
    on("approval_requested", (d) => { setApproval(d); setApprovedNote(null); });
    on("approved", (d) => { setApproval(null); setApprovedNote(d.channel === "voice" ? "Approved by voice" : "Approved on screen"); });
    on("order_status", (d) => setOrders((os) => {
      const i = os.findIndex((o) => o.order_id === d.order_id);
      return i < 0 ? [...os, d] : os.map((o, k) => (k === i ? { ...o, ...d } : o));
    }));
    on("fallback", (d) => setFallback(d.text));
    on("real_carts", (d) => setBasket((b) => (b ? { ...b, real_carts: d.carts } : b)));
    on("error", (d) => setError(d.message));
    es.onerror = () => {};
    return () => es.close();
  }, [sid]);

  const guard = useCallback(async <T,>(f: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true); setError(null);
    try { return await f(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }, []);

  const send = useCallback((text: string) => sid ? guard(() => api.message(sid, text)) : undefined, [sid, guard]);
  const applyOption = useCallback((i: number) => sid ? guard(() => api.editOption(sid, i)) : undefined, [sid, guard]);
  const split = useCallback((n: number) => sid ? guard(() => api.split(sid, n)) : undefined, [sid, guard]);
  const askApproval = useCallback(() => sid ? guard(() => api.requestApproval(sid)) : undefined, [sid, guard]);
  const addToCarts = useCallback(() => sid ? guard(() => api.handoff(sid)) : undefined, [sid, guard]);
  const approve = useCallback(async () => {
    if (!sid || !approval) return;
    await guard(async () => {
      const a = await api.approve(sid, approval.request_id);
      await api.checkout(sid, a.token);
    });
  }, [sid, approval, guard]);
  const delay = useCallback(() => sid ? guard(() => api.delay(sid)) : undefined, [sid, guard]);

  return { sid, messages, basket, orders, approval, approvedNote, fallback, busy, error, setError, send, applyOption, split, askApproval, addToCarts, approve, delay, setFallback, dismissApproval: () => setApproval(null) };
}
