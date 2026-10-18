"""Audio end-to-end test: joins the LiveKit room as the user, SPEAKS the demo (Azure TTS -> mic track),
and checks the worker's replies via the API. Needs API + stores + voice worker running.
    PYTHONPATH=. uv run python scripts/voice_e2e.py
"""

import asyncio
import os
import time

import azure.cognitiveservices.speech as speechsdk
import httpx
from dotenv import load_dotenv
from livekit import rtc

load_dotenv(".env")
API = os.environ.get("AGENTKART_API_URL", "http://localhost:8000")
SR = 16000

LINES = [
    "Help me shop for a birthday party for ten people tomorrow evening, under three thousand rupees. I already have plates.",
    "Chocolate.",
    "No, it doesn't need to be eggless.",
    "Yes, use my saved address.",
    "Okay, place the order.",
    "Wait, actually, change the cake.",  # must NOT order
    "Okay, place the order.",
    "Yes, place the order.",  # must order
]


def synth(text: str) -> bytes:
    cfg = speechsdk.SpeechConfig(
        subscription=os.environ["AZURE_SPEECH_KEY"], region=os.environ["AZURE_SPEECH_REGION"]
    )
    cfg.speech_synthesis_voice_name = "en-IN-PrabhatNeural"
    cfg.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Raw16Khz16BitMonoPcm
    )
    r = (
        speechsdk.SpeechSynthesizer(speech_config=cfg, audio_config=None)
        .speak_text_async(text)
        .get()
    )
    assert r.reason == speechsdk.ResultReason.SynthesizingAudioCompleted, r.reason
    return r.audio_data


async def speak(source: rtc.AudioSource, pcm: bytes) -> None:
    chunk = SR // 100 * 2  # 10 ms
    silence = bytes(chunk)
    for _ in range(30):
        await source.capture_frame(rtc.AudioFrame(silence, SR, 1, SR // 100))
    for i in range(0, len(pcm), chunk):
        part = pcm[i : i + chunk].ljust(chunk, b"\0")
        await source.capture_frame(rtc.AudioFrame(part, SR, 1, SR // 100))
        await asyncio.sleep(0.0095)
    for _ in range(120):  # trailing silence so endpointing fires
        await source.capture_frame(rtc.AudioFrame(silence, SR, 1, SR // 100))
        await asyncio.sleep(0.0095)


async def main() -> None:
    http = httpx.AsyncClient(base_url=API, timeout=30)
    sid = (await http.post("/sessions")).json()["session_id"]
    vs = (await http.post(f"/sessions/{sid}/voice")).json()
    print("session", sid, "room", vs["room"])

    room = rtc.Room()
    agent_audio = {"frames": 0}

    @room.on("track_subscribed")
    def _on_track(track, pub, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:

            async def drain():
                async for _ in rtc.AudioStream(track):
                    agent_audio["frames"] += 1

            asyncio.create_task(drain())

    await room.connect(vs["livekit_url"], vs["participant_token"])
    source = rtc.AudioSource(SR, 1)
    track = rtc.LocalAudioTrack.create_audio_track("mic", source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )

    async def history():
        return (await http.get(f"/sessions/{sid}")).json()

    t0 = time.time()
    while time.time() - t0 < 25:  # wait for greeting audio from the worker
        if agent_audio["frames"] > 50:
            break
        await asyncio.sleep(0.5)
    print(f"agent joined and spoke greeting: {agent_audio['frames']} audio frames received")
    await asyncio.sleep(4)

    for line in LINES:
        before = [m for m in (await history())["history"] if m["role"] == "assistant"]
        print(f"\nUSER (spoken): {line}")
        await speak(source, synth(line))
        for _ in range(
            80
        ):  # wait for a NEW assistant reply (user turn may be split by endpointing)
            await asyncio.sleep(0.5)
            now = [m for m in (await history())["history"] if m["role"] == "assistant"]
            if len(now) > len(before):
                await asyncio.sleep(2.5)  # allow a late second reply to land
                now = [m for m in (await history())["history"] if m["role"] == "assistant"]
                break
        heard = [m for m in (await history())["history"] if m["role"] == "user"][-1]["content"]
        print(f"  (STT heard)  : {heard}")
        for m in now[len(before) :]:
            print("AGENT        :", m["content"][:260])
        last = now[-1]["content"] if now else ""
        await asyncio.sleep(min(14, 2 + len(last) / 13))  # let the TTS finish before talking again
        if (await history())["orders"]:
            break
    snap = await history()
    print("\nORDERS:", [(o["store_name"], o["status"]) for o in snap["orders"]])
    print("USER heard from agent (frames):", agent_audio["frames"])
    await room.disconnect()


asyncio.run(main())
