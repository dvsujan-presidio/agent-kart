"""LiveKit voice worker: audio in/out only. Run: python -m voice.worker dev

STT/TTS = Azure AI Speech, VAD = Silero. Every user turn goes to the AgentKart API (same
orchestrator as typed chat); a spoken approval is judged by deterministic Python server-side.
The LLM slot holds a placeholder that is never called (llm_node is overridden).
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, JobProcess, WorkerOptions, cli
from livekit.agents.llm import StopResponse
from livekit.plugins import azure, silero

from voice.api_bridge import ApiBridge
from voice.dialog import VoiceDialog

load_dotenv(".env")
log = logging.getLogger("agentkart.voice")
AGENT_NAME = "agentkart-voice"
FILLER_AFTER_S = 1.3


class AgentKartAgent(Agent):
    """Each committed user turn starts exactly one API call; llm_node awaits THAT call's result.

    (Sharing a mutable 'reply' slot let a speculative generation consume the previous turn's reply,
    so the agent answered one turn late. Preemptive generation is also disabled in the session.)
    """

    def __init__(self, dialog: VoiceDialog):
        super().__init__(
            instructions="AgentKart voice front-end. Replies come from the AgentKart API."
        )
        self.dialog = dialog
        self._turn_lock = asyncio.Lock()  # turns are processed strictly in order
        self._pending: asyncio.Task | None = None

    async def _run_turn(self, text: str, conf: float | None) -> str:
        async with self._turn_lock:
            return await self.dialog.handle_user_turn(text, conf)

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        text = (new_message.text_content or "").strip()
        if not text:
            raise StopResponse()
        conf = getattr(new_message, "transcript_confidence", None)
        self._pending = asyncio.create_task(self._run_turn(text, conf))
        done, _ = await asyncio.wait({self._pending}, timeout=FILLER_AFTER_S)
        if not done:  # never leave silence while we search stores
            self.session.say("One moment, checking the stores.", add_to_chat_ctx=False)

    async def llm_node(self, chat_ctx, tools, model_settings):
        task, self._pending = self._pending, None
        if task is None:
            return  # nothing committed for this generation: stay silent rather than reuse an old reply
        reply = await task
        if reply:
            yield reply


async def _pump_events(bridge: ApiBridge, dialog: VoiceDialog, session: AgentSession) -> None:
    after = await bridge.event_cursor()
    while True:
        try:
            async for etype, data in bridge.events(after):
                text = dialog.on_event(etype, data)
                if text:
                    session.say(text)
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # reconnect on any stream error
            log.warning("event stream dropped: %s", e)
            await asyncio.sleep(2)
            after = await bridge.event_cursor()


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    sid = ctx.job.metadata or ctx.room.name
    bridge = ApiBridge(os.environ.get("AGENTKART_API_URL", "http://localhost:8000"), sid)
    dialog = VoiceDialog(bridge)
    langs = [x.strip() for x in os.environ.get("STT_LANGUAGES", "en-IN").split(",") if x.strip()]
    session = AgentSession(
        stt=azure.STT(language=langs if len(langs) > 1 else langs[0]),
        tts=azure.TTS(voice=os.environ.get("TTS_VOICE", "en-IN-NeerjaNeural"), language="en-IN"),
        vad=ctx.proc.userdata["vad"],
        # Azure STT finals arrive late and users pause mid-sentence: wait longer before closing a turn
        turn_handling={
            "endpointing": {"min_delay": 1.0, "max_delay": 4.0},
            "preemptive_generation": {
                "enabled": False
            },  # a reply must follow its own final transcript
        },
        llm=azure.responses.LLM(  # placeholder: required by the framework, never invoked
            model="gpt-5.6-luna",
            azure_endpoint=os.environ.get("MODEL_ENDPOINT"),
            azure_deployment=os.environ.get("MODEL_DEPLOYMENT", "gpt-5.6-luna"),
            api_version=os.environ.get("MODEL_API_VERSION"),
            api_key=os.environ.get("MODEL_API_KEY"),
        ),
    )
    await session.start(agent=AgentKartAgent(dialog), room=ctx.room)
    pump = asyncio.create_task(_pump_events(bridge, dialog, session))
    ctx.add_shutdown_callback(lambda: pump.cancel())
    greeting = await bridge.greeting()
    session.say(greeting or "Hi, I'm AgentKart. What are you planning?")


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm, agent_name=AGENT_NAME)
    )
