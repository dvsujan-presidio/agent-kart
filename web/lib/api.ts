/* eslint-disable @typescript-eslint/no-explicit-any */
import type { VoiceSession } from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail ?? detail; } catch {}
    throw new Error(detail);
  }
  return r.json() as Promise<T>;
}
const post = <T,>(p: string, body?: unknown) => j<T>(p, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  newSession: () => post<{ session_id: string }>("/sessions", { channel: "web" }),
  snapshot: (sid: string) => j<any>(`/sessions/${sid}`),
  message: (sid: string, text: string) => post<{ reply: string; approval_request: any }>(`/sessions/${sid}/messages`, { text, channel: "web" }),
  editOption: (sid: string, index: number) => post<any>(`/sessions/${sid}/basket/edit`, { action: "apply_option", index }),
  split: (sid: string, payers: number) => post<any>(`/sessions/${sid}/split`, { payers }),
  handoff: (sid: string) => post<{ reply: string; carts: any[] }>(`/sessions/${sid}/handoff`),
  requestApproval: (sid: string) => post<any>(`/sessions/${sid}/approval-request`),
  approve: (sid: string, request_id: string) => post<{ token: string }>(`/sessions/${sid}/approve`, { request_id, channel: "web" }),
  checkout: (sid: string, token: string) => post<{ orders: any[] }>(`/sessions/${sid}/checkout`, { token }),
  voice: (sid: string) => post<VoiceSession>(`/sessions/${sid}/voice`),
  delay: (sid: string) => post<any>("/demo/delay", { session_id: sid, store_id: "cakecorner" }),
  reset: () => post<any>("/demo/reset"),
};
