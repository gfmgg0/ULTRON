"""
Amazon Alexa Brasil native integration plugin for ULTRON (`alexa_control`).

Works directly with Amazon Brasil (`amazon.com.br` / `alexa.amazon.com.br`)
without needing Voice Monkey or any US-only skill!

Capabilities:
  - status: check Amazon Brasil connection, discovered Echo devices, and local webhook endpoints
  - authenticate: open a browser window to log into `amazon.com.br` and automatically save session cookies & Echo devices
  - list_devices: list all Echo / Fire TV / Alexa devices on the user's Amazon account
  - speak / announce: make an Echo device speak any sentence in Portuguese (`Alexa.Speak`)
  - text_command: send ANY voice command in Portuguese directly to Alexa (`Alexa.TextCommand`, e.g., "apagar luz da sala", "ligar ar condicionado", "tocar rock no Spotify")
  - list_routines: list all routines configured in the user's Alexa app
  - trigger_routine: execute an Alexa routine or voice trigger
  - volume: adjust volume (0-100) on an Echo device
"""
from __future__ import annotations

from core import outcome
from plugins._alexa_core import (
    ALEXA_PLUGIN_SETTINGS,
    alexa_connect_bluetooth_speaker,
    alexa_disconnect_bluetooth_speaker,
    alexa_list_routines,
    alexa_set_volume,
    alexa_set_wake_word,
    alexa_speak,
    alexa_start_dropin,
    alexa_stop_dropin,
    alexa_text_command,
    alexa_trigger_routine,
    authenticate_amazon_browser,
    fetch_echo_devices,
    fetch_recent_voice_history,
    get_alexa_status,
)

PLUGIN_SETTINGS = ALEXA_PLUGIN_SETTINGS

PLUGIN = {
    "name": "alexa_control",
    "tier": "core",
    "brief": "Native Amazon Alexa Brasil control: Drop In continuous mic mode, Bluetooth voice routing, Echo mic listener, TTS, smart home commands, and routines.",
    "description": (
        "Integra o ULTRON diretamente à conta Amazon Alexa Brasil (amazon.com.br) sem precisar de "
        "nenhuma skill externa: iniciar/encerrar Modo Drop In de escuta contínua entre Echos para "
        "falar 'Ultron' sem dizer 'Alexa' (start_dropin, stop_dropin), conectar a voz original do "
        "ULTRON na Alexa via Bluetooth (connect_bluetooth, disconnect_bluetooth), consultar histórico "
        "de voz falado no microfone do Echo (voice_history), alterar wake word física do Echo "
        "(set_wake_word), conectar conta Amazon pelo navegador (authenticate), consultar estado "
        "(status), listar aparelhos Echo (list_devices), fazer o Echo falar qualquer frase em voz alta "
        "(speak, announce), enviar qualquer comando em português para a Alexa executar na casa inteligente "
        "ou música (text_command: ex. 'acender luz da sala', 'ligar ar condicionado', 'tocar música'), "
        "listar rotinas (list_routines), disparar rotina (trigger_routine) e ajustar volume do Echo (volume)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "status",
                    "authenticate",
                    "start_dropin",
                    "stop_dropin",
                    "connect_bluetooth",
                    "disconnect_bluetooth",
                    "set_wake_word",
                    "voice_history",
                    "list_devices",
                    "speak",
                    "announce",
                    "text_command",
                    "list_routines",
                    "trigger_routine",
                    "volume",
                ],
                "description": "Ação a executar na Amazon Alexa.",
            },
            "message": {
                "type": "STRING",
                "description": "Frase que o Echo deve falar (speak, announce) ou comando em português que a Alexa deve executar (text_command).",
            },
            "device": {
                "type": "STRING",
                "description": "Nome do dispositivo Echo de destino (opcional; usa o Echo principal automaticamente se omitido).",
            },
            "routine": {
                "type": "STRING",
                "description": "Nome da rotina ou comando para 'trigger_routine'.",
            },
            "volume_level": {
                "type": "INTEGER",
                "description": "Nível de volume de 0 a 100 para 'volume'.",
            },
        },
        "required": ["action"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()
    device = str(params.get("device") or "").strip()

    try:
        if action == "status":
            st = get_alexa_status()
            bt = st.get("bluetooth_echo") or {}
            return outcome.done(
                "alexa_status",
                amazon_brasil_connected=st["amazon_brasil_connected"],
                echo_devices=", ".join(st["echo_devices"]) if st["echo_devices"] else "none",
                default_echo=st["default_echo_device"],
                ultron_voice_on_echo_bluetooth=bt.get("ultron_voice_on_echo", False),
                bluetooth_device=bt.get("paired_name") or "none",
                webhook_endpoint=st["webhook_endpoint"],
                last_command_from_alexa=st.get("last_command_from_alexa") or "none",
            )

        if action == "start_dropin":
            target_dev = device or str(params.get("message") or "Echo Dot Sala").strip()
            ok, details = alexa_start_dropin(target_device=target_dev)
            if ok:
                return outcome.done("alexa_start_dropin", target=target_dev, details=details)
            return outcome.failed("alexa_start_dropin", details)

        if action == "stop_dropin":
            ok, details = alexa_stop_dropin(bridge_device=device or "Echo Pop de Gabriel")
            if ok:
                return outcome.done("alexa_stop_dropin", details=details)
            return outcome.failed("alexa_stop_dropin", details)

        if action == "set_wake_word":
            ww = str(params.get("message") or params.get("routine") or "ECHO").strip()
            ok, details = alexa_set_wake_word(wake_word=ww, device=device)
            if ok:
                return outcome.done("alexa_set_wake_word", wake_word=ww, details=details)
            return outcome.failed("alexa_set_wake_word", details)

        if action == "connect_bluetooth":
            lvl = int(params.get("volume_level") if params.get("volume_level") is not None else 85)
            ok, details = alexa_connect_bluetooth_speaker(device=device, volume_pct=lvl)
            if ok:
                return outcome.done("alexa_connect_bluetooth", details=details)
            return outcome.failed("alexa_connect_bluetooth", details)

        if action == "disconnect_bluetooth":
            ok, details = alexa_disconnect_bluetooth_speaker()
            if ok:
                return outcome.done("alexa_disconnect_bluetooth", details=details)
            return outcome.failed("alexa_disconnect_bluetooth", details)

        if action == "voice_history":
            recs = fetch_recent_voice_history(limit=10)
            if not recs:
                return outcome.done("alexa_voice_history", count=0, details="Nenhum comando recente encontrado.")
            lines = [
                f"- [{r['device_name']}] \"{r['transcript']}\" -> Alexa: \"{r['alexa_response']}\""
                for r in recs
            ]
            return outcome.done("alexa_voice_history", count=len(recs)) + "\n" + "\n".join(lines)

        if action == "authenticate":
            ok, details = authenticate_amazon_browser()
            if ok:
                return outcome.done("alexa_authenticate", details=details)
            return outcome.failed("alexa_authenticate", details)

        if action == "list_devices":
            ok, devs, msg = fetch_echo_devices()
            if not ok:
                return outcome.failed("alexa_list_devices", msg)
            lines = [
                f"- {d.get('accountName', 'Echo')} | Família={d.get('deviceFamily', '')} | Online={d.get('online', False)}"
                for d in devs
            ]
            return outcome.done("alexa_list_devices", count=len(devs)) + "\n" + "\n".join(lines)

        if action in ("speak", "announce"):
            msg = str(params.get("message") or params.get("routine") or "").strip()
            ok, details = alexa_speak(text=msg, device=device)
            if ok:
                return outcome.done("alexa_speak", device=device or "default", details=details)
            return outcome.failed("alexa_speak", details)

        if action == "text_command":
            cmd = str(params.get("message") or params.get("routine") or "").strip()
            ok, details = alexa_text_command(command_text=cmd, device=device)
            if ok:
                return outcome.done("alexa_text_command", command=cmd, device=device or "default", details=details)
            return outcome.failed("alexa_text_command", details)

        if action == "list_routines":
            ok, routines, msg = alexa_list_routines()
            if not ok:
                return outcome.failed("alexa_list_routines", msg)
            names = [r.get("name") or "(Sem nome)" for r in routines if isinstance(r, dict)]
            return outcome.done("alexa_list_routines", count=len(names), routines=", ".join(names[:30]))

        if action == "trigger_routine":
            routine = str(params.get("routine") or params.get("message") or "").strip()
            ok, details = alexa_trigger_routine(routine_id_or_name=routine, device=device)
            if ok:
                return outcome.done("alexa_trigger_routine", routine=routine, details=details)
            return outcome.failed("alexa_trigger_routine", details)

        if action == "volume":
            lvl = int(params.get("volume_level") if params.get("volume_level") is not None else 50)
            ok, details = alexa_set_volume(volume=lvl, device=device)
            if ok:
                return outcome.done("alexa_volume", volume=lvl, device=device or "default", details=details)
            return outcome.failed("alexa_volume", details)

        return outcome.failed("alexa_control", f"Ação desconhecida: {action}")
    except Exception as exc:
        return outcome.failed("alexa_control", f"Erro na integração com a Alexa ({action}): {exc}")
