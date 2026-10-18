export function money(minor: number | null | undefined, cur: "INR" | "USD" = "INR"): string {
  if (minor == null) return "unknown";
  const major = Math.trunc(minor / 100), part = Math.abs(minor % 100);
  const locale = cur === "INR" ? "en-IN" : "en-US";
  const s = new Intl.NumberFormat(locale).format(major);
  const sym = cur === "INR" ? "₹" : "$";
  return part ? `${sym}${s}.${String(part).padStart(2, "0")}` : `${sym}${s}`;
}
export function when(iso: string | null | undefined): string {
  if (!iso) return "at checkout";
  const d = new Date(iso), now = new Date();
  const days = Math.round((new Date(d.toDateString()).getTime() - new Date(now.toDateString()).getTime()) / 86400000);
  const day = days === 0 ? "today" : days === 1 ? "tomorrow" : d.toLocaleDateString("en-IN", { weekday: "long" });
  return `${d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit", hour12: true })} ${day}`;
}
