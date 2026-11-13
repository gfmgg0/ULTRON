"""
Google Home / Google Nest / Chromecast integration plugin for ULTRON (`google_home_control`).

Capabilities:
  - discover: discover Google Cast / Google Home / Nest / Android TV devices on the local LAN
  - speak: speak a TTS message in Portuguese on a Google Home / Nest / Cast device
  - cast_media: cast an audio or video URL to a Google Home / Chromecast device
  - volume: set the volume level (0-100) on a Google Cast device
  - stop: stop media playback on a Google Cast device
"""
from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from core import outcome
from plugins._google_core import SHARED_PLUGIN_SETTINGS

PLUGIN_SETTINGS = SHARED_PLUGIN_SETTINGS

ROOT = Path(__file__).resolve().parent.parent
TCL_CONFIG = ROOT / "config" / "integrations" / "tcl.json"

PLUGIN = {
    "name": "google_home_control",
    "tier": "extra",
    "brief": "Discover and control Google Home, Google Nest, and Chromecast devices on the local network.",
    "description": (
        "Integra o ULTRON ao ambiente Google Home, Google Nest e Chromecast na rede local de Gabriel: "
        "descobrir caixas de som e telas Google Cast na rede (discover), fazer um Google Home/Nest "
        "falar um aviso em voz alta (speak), transmitir áudio ou vídeo via Cast (cast_media), "
        "ajustar volume (volume) e parar reprodução (stop)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["discover", "speak", "cast_media", "volume", "stop"],
                "description": "Ação a executar nos dispositivos Google Home / Cast.",
            },
            "device": {
                "type": "STRING",
                "description": "Nome ou IP do dispositivo Google Home / Nest / Cast (se omitido, usa o primeiro encontrado).",
            },
            "message": {
                "type": "STRING",
                "description": "Frase para o Google Home falar em voz alta (para 'speak').",
            },
            "media_url": {
                "type": "STRING",
                "description": "URL de áudio/vídeo para transmitir em 'cast_media'.",
            },
            "content_type": {
                "type": "STRING",
                "description": "Tipo MIME da mídia em 'cast_media' (ex.: 'audio/mp3' ou 'video/mp4').",
            },
            "level": {
                "type": "INTEGER",
                "description": "Nível de volume de 0 a 100 para 'volume'.",
            },
        },
        "required": ["action"],
    },
}


def _probe_eureka(ip: str) -> dict[str, Any] | None:
    for port, scheme in ((8008, "http"), (8443, "https")):
        try:
            resp = httpx.get(
                f"{scheme}://{ip}:{port}/setup/eureka_info?options=detail",
                verify=False,
                timeout=1.5,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ip": ip,
                    "name": data.get("name") or ip,
                    "model": data.get("detail", {}).get("model_name") or "Google Cast",
                }
        except Exception:
            pass
    # Also check if Cast TLS port 8009 is open
    try:
        with socket.create_connection((ip, 8009), timeout=0.8):
            return {"ip": ip, "name": ip, "model": "Google Cast / Android TV"}
    except Exception:
        return None


def _discover_cast_devices() -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    seen_ips: set[str] = set()

    # 1. Try avahi-browse for _googlecast._tcp if installed on Linux
    try:
        r = subprocess.run(
            ["avahi-browse", "-rtkp", "_googlecast._tcp"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for line in (r.stdout or "").splitlines():
            if line.startswith("="):
                parts = line.split(";")
                if len(parts) >= 8:
                    ip = parts[7]
                    name = parts[3]
                    if ip and "." in ip and ip not in seen_ips:
                        seen_ips.add(ip)
                        devices.append({"ip": ip, "name": name, "model": "Google Cast"})
    except Exception:
        pass

    # 2. Check known TCL Google TV IP
    if TCL_CONFIG.is_file():
        try:
            tcl = json.loads(TCL_CONFIG.read_text(encoding="utf-8"))
            host = tcl.get("host", "")
            if host and host not in seen_ips:
                probed = _probe_eureka(host)
                if probed:
                    probed["name"] = tcl.get("name") or probed["name"]
                    seen_ips.add(host)
                    devices.append(probed)
        except Exception:
            pass

    return devices


def _get_pychromecast_device(target: str = ""):
    import pychromecast  # type: ignore

    target_clean = (target or "").strip()
    if target_clean and all(p.isdigit() for p in target_clean.split(".")) and target_clean.count(".") == 3:
        casts, browser = pychromecast.get_chromecasts(known_hosts=[target_clean], timeout=4)
    elif target_clean:
        casts, browser = pychromecast.get_listed_chromecasts(friendly_names=[target_clean], timeout=4)
        if not casts:
            casts, browser = pychromecast.get_chromecasts(timeout=4)
    else:
        known = []
        if TCL_CONFIG.is_file():
            try:
                known = [json.loads(TCL_CONFIG.read_text(encoding="utf-8")).get("host", "")]
            except Exception:
                pass
        casts, browser = pychromecast.get_chromecasts(known_hosts=[h for h in known if h] or None, timeout=4)
    if not casts:
        pychromecast.discovery.stop_discovery(browser)
        return None, None
    cast = casts[0]
    cast.wait(timeout=5)
    return cast, browser


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "discover").strip().lower()
    device_arg = str(params.get("device") or "").strip()

    try:
        if action == "discover":
            found = _discover_cast_devices()
            if not found:
                return outcome.done(
                    "google_home_discover",
                    count=0,
                    summary="Nenhum dispositivo Google Cast/Home respondeu na varredura rápida da rede local.",
                )
            desc = "; ".join(f"{d['name']} ({d['ip']} - {d['model']})" for d in found)
            return outcome.done("google_home_discover", count=len(found), devices=desc)

        try:
            cast, browser = _get_pychromecast_device(device_arg)
        except ImportError:
            return outcome.failed(
                "google_home_control",
                "Para transmitir áudio/TTS direto via protocolo Cast, instale o pacote opcional: pip install pychromecast",
            )

        if cast is None:
            return outcome.failed(
                "google_home_control",
                f"Nenhum dispositivo Google Home / Cast encontrado ({device_arg or 'rede local'}).",
            )

        try:
            if action == "speak":
                msg = str(params.get("message") or "").strip()
                if not msg:
                    return outcome.failed("google_home_speak", "Informe 'message' com o texto que o Google Home deve falar.")
                tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&client=tw-ob&tl=pt-BR&q={quote(msg[:200])}"
                mc = cast.media_controller
                mc.play_media(tts_url, "audio/mp3")
                mc.block_until_active(timeout=5)
                return outcome.done("google_home_speak", device=cast.name, message=msg)

            if action == "cast_media":
                url = str(params.get("media_url") or "").strip()
                ctype = str(params.get("content_type") or "audio/mp3").strip()
                if not url:
                    return outcome.failed("google_home_cast", "Informe 'media_url' com o link da mídia.")
                mc = cast.media_controller
                mc.play_media(url, ctype)
                mc.block_until_active(timeout=5)
                return outcome.done("google_home_cast", device=cast.name, media_url=url)

            if action == "volume":
                lvl = max(0, min(100, int(params.get("level") if params.get("level") is not None else 50)))
                cast.set_volume(lvl / 100.0)
                return outcome.done("google_home_volume", device=cast.name, volume_percent=lvl)

            if action == "stop":
                cast.quit_app()
                return outcome.done("google_home_stop", device=cast.name)
        finally:
            try:
                import pychromecast
                if browser:
                    pychromecast.discovery.stop_discovery(browser)
            except Exception:
                pass

        return outcome.failed("google_home_control", f"Ação desconhecida: {action}")
    except Exception as exc:
        return outcome.failed("google_home_control", f"Erro no controle Google Home/Cast ({action}): {exc}")

