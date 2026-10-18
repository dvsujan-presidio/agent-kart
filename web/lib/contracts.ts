/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

export interface Address {
  line1: string;
  area?: string | null;
  city: string;
  pincode: string;
  country?: string;
}
export interface Approval {
  basket_hash: string;
  approved_at: string;
  channel: "web" | "voice";
  request_id: string;
  confirmation_utterance?: string | null;
  token: string;
}
export interface ApprovalRequest {
  request_id: string;
  session_id: string;
  basket_hash: string;
  readback: string;
  expires_at: string;
}
export interface Basket {
  lines: BasketLine[];
  fees_by_store: {
    [k: string]: number | null;
  };
  discounts_minor?: number;
  total_minor: number;
  total_is_estimate?: boolean;
  budget_minor: number;
  currency: "INR" | "USD";
  excluded?: Exclusion[];
  feasible?: boolean;
  tradeoffs?: TradeOff[];
  hash: string;
}
export interface BasketLine {
  offer: Offer;
  packs: number;
  line_total_minor: number;
}
export interface Offer {
  store_id: string;
  source: "ucp_mock" | "ucp_real";
  product_id: string;
  variant_id: string;
  title: string;
  category: string;
  pack_size: number;
  unit: string;
  price_minor: number;
  currency: "INR" | "USD";
  rating?: number | null;
  eta?: string | null;
  in_stock?: boolean;
  discount?: Discount | null;
  url?: string | null;
}
export interface Discount {
  code: string;
  amount_minor: number;
}
export interface Exclusion {
  offer: Offer;
  reason: "late" | "out_of_stock" | "user_excluded";
}
export interface TradeOff {
  title: string;
  delta_minor: number;
  basket: Basket;
}
export interface Goal {
  scenario: string;
  occasion: string;
  guests: number;
  budget_minor: number;
  currency: "INR" | "USD";
  deadline: string;
  address?: Address | null;
  exclusions?: string[];
  preferences?: {
    [k: string]: unknown;
  };
  payers?: number;
}
export interface ListItem {
  category: string;
  need_qty: number;
  unit: string;
  rule: string;
  required?: boolean;
}
export interface OrderStatus {
  store_id: string;
  order_id: string;
  status: "placed" | "packed" | "out_for_delivery" | "delayed" | "delivered";
  eta: string;
}
export interface PriceCheck {
  retailer: string;
  query: string;
  indicative_price_minor?: number | null;
  currency?: "INR" | "USD";
  source_url: string;
  snippet: string;
  is_estimate?: boolean;
}
export interface RealCart {
  store_id: string;
  store_domain: string;
  ucp_cart_id?: string | null;
  lines: BasketLine[];
  subtotal_minor: number;
  shipping_estimate_minor?: number | null;
  currency?: "INR" | "USD";
  handoff_url?: string | null;
  handoff_kind?: ("cart_continue_url" | "permalink") | null;
  degraded?: string[];
}
export interface Split {
  payers: number;
  shares_minor: number[];
}
export interface StoreTerms {
  store_id: string;
  delivery_fee_minor?: number | null;
  free_delivery_above_minor?: number | null;
  min_order_minor?: number | null;
}
export interface VoiceSession {
  livekit_url: string;
  room: string;
  participant_token: string;
  agent_name?: string;
}
