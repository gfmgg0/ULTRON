"""
Local wake-word detection for ULTRON ("Ultron" / "Oi Ultron" / "Hey Ultron").

Design goals:
  • Native "ULTRON" wake word in Portuguese & English using `faster_whisper` (tiny int8)
    with fast RMS voice-activity gating (near-zero CPU during silence, ~80 ms check on
    short speech bursts), plus optional `openwakeword` fallback.
  • ZERO latency on the audio path — the microphone callback only ever does a
    cheap, non-blocking queue push (feed()); the actual model inference runs in
    this module's own background thread, so the real-time audio thread and the
    Gemini stream are never slowed.
  • If the user says a full command in one breath while ULTRON is sleeping
    (e.g. "Ultron, que horas são?"), it wakes ULTRON AND forwards the spoken
    question automatically so the user does not have to repeat it!
"""
from __future__ import annotations

import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

WAKE_MODEL = "hey_jarvis"
WHISPER_WAKE_MODEL = "tiny"
DEFAULT_THRESHOLD = 0.5
SAMPLE_RATE = 16000

_ULTRON_WAKE_RE = re.compile(
    r"\b(?:oi\s+|ei\s+|hey\s+|ok\s+|fala\s+)?(?:ultron|utron|ultrão|ultram|otron|jarvis)\b[\s,.:;?!-]*(.*)$",
    re.IGNORECASE,
)


def _has_faster_whisper() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("faster_whisper") is not None
    except Exception:
        return False


def _has_whisper_tiny_cached() -> bool:
    hub_dir = Path.home() / ".cache" / "huggingface" / "hub"
    if not hub_dir.is_dir():
        return False
    return any(
        p.is_dir() and "whisper-tiny" in p.name.lower() and any(p.rglob("model.bin"))
        for p in hub_dir.iterdir()
    )


def is_installed() -> bool:
    """True if faster_whisper or openwakeword is importable."""
    if _has_faster_whisper():
        return True
    try:
        import importlib.util
        return importlib.util.find_spec("openwakeword") is not None
    except Exception:
        return False


def is_ready() -> bool:
    """True if the 'Ultron' Whisper wake model (or openwakeword model) is cached on disk."""
    if _has_faster_whisper() and _has_whisper_tiny_cached():
        return True
    try:
        import openwakeword
        models_dir = Path(openwakeword.__file__).resolve().parent / "resources" / "models"
        if not models_dir.is_dir():
            return False
        has_wake = (any(models_dir.glob(f"{WAKE_MODEL}*.onnx"))
                    or any(models_dir.glob(f"{WAKE_MODEL}*.tflite")))
        has_mel = (any(models_dir.glob("melspectrogram*.onnx"))
                   or any(models_dir.glob("melspectrogram*.tflite")))
        has_emb = (any(models_dir.glob("embedding_model*.onnx"))
                   or any(models_dir.glob("embedding_model*.tflite")))
        return bool(has_wake and has_mel and has_emb)
    except Exception:
        return False


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """
    One-click setup for the UI button: ensure faster-whisper tiny model is downloaded
    for 'Ultron' wake-word detection.
    """
    _tell = notify or (lambda _msg: None)
    try:
        if not _has_faster_whisper():
            logger("Wake word: installing faster-whisper…")
            _tell("Wake word: installing faster-whisper…")
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "faster-whisper"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
                return False, f"pip install failed: {tail[0][:160]}"

        logger("Wake word: downloading 'Ultron' speech model (Whisper tiny)…")
        _tell("Wake word: downloading 'Ultron' speech model…")
        from core.network import prefer_api_ipv4
        prefer_api_ipv4()
        from faster_whisper import WhisperModel
        WhisperModel(WHISPER_WAKE_MODEL, device="cpu", compute_type="int8")

        if is_ready():
            logger("Wake word 'Ultron': ready.")
            return True, "Wake word 'Ultron' instalado e pronto."
        return False, "Modelo baixado, mas não pôde ser verificado."
    except Exception as e:
        return False, f"setup error: {e}"


class WakeWordDetector:
    """
    Runs the 'Ultron' wake-word detector in a dedicated background thread.
    The mic thread calls feed() with raw int16 frames; detections invoke on_detect().
    """

    def __init__(self, on_detect: Callable[[], None],
                 threshold: float = DEFAULT_THRESHOLD,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._threshold = threshold
        self._logger    = logger
        self._notify    = notify or (lambda _msg: None)
        self._queue: queue.Queue = queue.Queue(maxsize=80)
        self._thread: threading.Thread | None = None
        self._running = False
        self._whisper = None
        self._oww_model = None
        self._ready = False

    def start(self) -> bool:
        """Load the wake model and spawn the inference thread."""
        if self._running:
            return True
        if _has_faster_whisper():
            try:
                from core.network import prefer_api_ipv4
                prefer_api_ipv4()
                from faster_whisper import WhisperModel
                self._whisper = WhisperModel(WHISPER_WAKE_MODEL, device="cpu", compute_type="int8")
            except Exception as e:
                self._logger(f"Wake word (Whisper): could not load model — {e}")
                self._whisper = None

        if self._whisper is None:
            try:
                from openwakeword.model import Model
                self._oww_model = Model(wakeword_models=[WAKE_MODEL], inference_framework="onnx")
            except Exception as e:
                self._logger(f"Wake word: could not load model — {e}")
                self._notify("Wake word unavailable — use the WAKE NOW button.")
                return False

        self._running = True
        self._ready = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WakeWordThread")
        self._thread.start()
        self._logger("Wake word: escutando a palavra de ativação 'Ultron'.")
        return True

    def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        self._whisper = None
        self._oww_model = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def feed(self, frame_int16) -> None:
        """Called from the mic callback (real-time thread). Non-blocking."""
        if not self._running:
            return
        try:
            data = frame_int16[:, 0].copy() if getattr(frame_int16, "ndim", 1) > 1 else frame_int16.copy()
            self._queue.put_nowait(data)
        except queue.Full:
            pass
        except Exception:
            pass

    def _forward_trailing_command(self, cmd: str) -> None:
        """If the user said 'Ultron, <command>' in one breath, send <command> to ULTRON."""
        if not cmd or len(cmd.strip()) < 2:
            return
        try:
            import httpx
            from plugins._alexa_core import get_settings
            cfg = get_settings()
            httpx.post(
                "http://127.0.0.1:8000/api/alexa/webhook",
                headers={"X-Ultron-Key": cfg["alexa_webhook_key"]},
                json={"command": cmd.strip(), "device": "WakeWord Ultron"},
                timeout=3.0,
            )
        except Exception:
            pass

    def _loop(self) -> None:
        import numpy as np

        if self._whisper is not None:
            speech_chunks: list[np.ndarray] = []
            speech_samples = 0
            silence_samples = 0
            in_speech = False
            rms_gate = 280.0
            min_speech_samples = int(SAMPLE_RATE * 0.32)   # 320 ms
            max_speech_samples = int(SAMPLE_RATE * 2.20)   # 2.2 s max window
            pause_samples_needed = int(SAMPLE_RATE * 0.28) # 280 ms pause triggers check

            while self._running:
                try:
                    frame = self._queue.get()
                    if frame is None or not self._running:
                        break
                    arr = np.asarray(frame, dtype=np.int16)
                    if arr.size == 0:
                        continue
                    rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))
                    if rms >= rms_gate:
                        in_speech = True
                        silence_samples = 0
                        speech_chunks.append(arr)
                        speech_samples += arr.size
                    elif in_speech:
                        speech_chunks.append(arr)
                        speech_samples += arr.size
                        silence_samples += arr.size

                    should_eval = in_speech and (
                        (speech_samples >= min_speech_samples and silence_samples >= pause_samples_needed)
                        or speech_samples >= max_speech_samples
                    )
                    if should_eval:
                        audio_i16 = np.concatenate(speech_chunks)
                        speech_chunks.clear()
                        speech_samples = 0
                        silence_samples = 0
                        in_speech = False

                        audio_f32 = audio_i16.astype(np.float32) / 32768.0
                        segments, _ = self._whisper.transcribe(
                            audio_f32,
                            language="pt",
                            beam_size=1,
                            best_of=1,
                            condition_on_previous_text=False,
                            initial_prompt="Ultron, Oi Ultron, Ei Ultron, Jarvis.",
                            vad_filter=False,
                        )
                        text = " ".join(s.text for s in segments).strip()
                        if text:
                            m = _ULTRON_WAKE_RE.search(text)
                            if m:
                                trailing = (m.group(1) or "").strip()
                                self._logger(f"Wake word 'Ultron' detectado: \"{text}\"")
                                self._drain()
                                try:
                                    self._on_detect()
                                except Exception as e:
                                    self._logger(f"Wake word: on_detect error — {e}")
                                if trailing:
                                    threading.Thread(
                                        target=self._forward_trailing_command,
                                        args=(trailing,),
                                        daemon=True,
                                    ).start()
                except Exception as e:
                    self._logger(f"Wake word (Whisper): inference error — {e}")
            return

        # Fallback: openwakeword
        while self._running:
            try:
                frame = self._queue.get()
                if frame is None or not self._running:
                    break
                scores = self._oww_model.predict(np.asarray(frame, dtype=np.int16))
                score = 0.0
                if isinstance(scores, dict):
                    for k, v in scores.items():
                        if "jarvis" in k.lower():
                            score = max(score, float(v))
                    if score == 0.0 and scores:
                        score = max(float(v) for v in scores.values())
                if score >= self._threshold:
                    self._drain()
                    try:
                        self._on_detect()
                    except Exception as e:
                        self._logger(f"Wake word: on_detect error — {e}")
            except Exception as e:
                self._logger(f"Wake word: inference error — {e}")

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            pass
