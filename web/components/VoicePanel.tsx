"use client";
import { BarVisualizer, LiveKitRoom, RoomAudioRenderer, useLocalParticipant, useVoiceAssistant } from "@livekit/components-react";
import "@livekit/components-styles";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { VoiceSession } from "@/lib/types";

const LABEL: Record<string, string> = {
  disconnected: "Offline", connecting: "Connecting…", initializing: "Waking up AgentKart…",
  listening: "Listening…", thinking: "Thinking…", speaking: "Speaking…",
};

export function VoicePanel({ sid }: { sid: string | null }) {
  const [vs, setVs] = useState<VoiceSession | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    const h = () => document.getElementById("agentkart-voice-start")?.click();
    window.addEventListener("agentkart:voice", h);
    return () => window.removeEventListener("agentkart:voice", h);
  }, []);

  const start = async () => {
    if (!sid) return;
    setStarting(true); setErr(null);
    try { setVs(await api.voice(sid)); } catch (e) { setErr((e as Error).message); } finally { setStarting(false); }
  };

  if (!vs) {
    return (
      <div className="flex items-center gap-3">
        <button id="agentkart-voice-start" onClick={start} disabled={!sid || starting}
          className="flex items-center gap-2 rounded-full bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40">
          🎙️ {starting ? "Starting…" : "Talk to AgentKart"}
        </button>
        {err && <span className="text-xs text-red-600">{err}</span>}
      </div>
    );
  }
  return (
    <LiveKitRoom serverUrl={vs.livekit_url} token={vs.participant_token} connect audio video={false}
      onDisconnected={() => setVs(null)} onError={(e) => setErr(e.message)}>
      <RoomAudioRenderer />
      <Live onEnd={() => setVs(null)} />
    </LiveKitRoom>
  );
}

function Live({ onEnd }: { onEnd: () => void }) {
  const { state, audioTrack } = useVoiceAssistant();
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant();
  return (
    <div className="flex items-center gap-3 rounded-full border border-emerald-300 bg-emerald-50 px-3 py-1.5 dark:border-emerald-800 dark:bg-emerald-950">
      <div className="h-8 w-20"><BarVisualizer state={state} barCount={5} trackRef={audioTrack} className="agent-bars" style={{ height: 32 }} /></div>
      <span className="min-w-28 text-sm font-medium">{LABEL[state] ?? state}</span>
      <button onClick={() => localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)} className="rounded-full border px-2.5 py-1 text-xs">
        {isMicrophoneEnabled ? "🎙️ Mute" : "🔇 Unmute"}
      </button>
      <button onClick={onEnd} className="rounded-full bg-red-600 px-2.5 py-1 text-xs text-white">End</button>
    </div>
  );
}
