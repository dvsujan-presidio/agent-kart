export type Line = {
  store_id: string; store_name: string; title: string; category: string; packs: number;
  unit_price_minor: number; line_total_minor: number; eta: string | null; on_time: boolean; rule?: string;
  image_url?: string | null; url?: string | null;
};
export type RealCart = {
  store_id: string; store_name?: string; store_domain: string; ucp_cart_id: string | null; subtotal_minor: number;
  currency: "USD"; handoff_url: string | null; degraded: string[]; lines: { offer: { title: string }; packs: number; line_total_minor: number }[];
};
export type Option = { index: number; title: string; delta_minor: number; new_total_minor: number; within_budget: boolean };
export type Basket = {
  hash: string; currency: "INR" | "USD"; total_minor: number; budget_minor: number; feasible: boolean;
  estimate: boolean; fees: Record<string, number | null>; lines: Line[]; deadline: string | null;
  excluded: { store_name: string; title: string; reason: string; eta: string | null }[];
  late_notes: { store_name: string; category: string; cheaper_by_minor: number; eta: string }[];
  options: Option[]; insight: { saving_minor: number; optimal_stores: number; naive_stores: number } | null;
  payers: number; shares_minor: number[] | null; missing_required: string[]; notes: string[];
  guests: number; address: string | null; mode: "demo" | "real"; real_carts: RealCart[];
};
export type Order = {
  order_id: string; store_id: string; store_name: string; status: string; eta: string;
  total_minor: number; items: string[]; kind: "main" | "backup"; replaced?: boolean;
};
export type ChatMsg = { role: "user" | "assistant"; text: string; fallback?: boolean; channel?: string };
export type ApprovalReq = { kind: "main" | "backup"; request_id: string; readback: string; expires_at: string; basket: Basket | null };
export type VoiceSession = { livekit_url: string; room: string; participant_token: string; agent_name: string };
