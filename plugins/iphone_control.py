"""
iPhone / iOS / iCloud integration plugin for ULTRON (`iphone_control`).

Capabilities:
  - status: check iPhone connectivity (Wi-Fi LAN, USB, Bluetooth), battery/telemetry from iOS Shortcuts, and webhook details
  - notify: send a push notification, message, or clickable link directly to the iPhone
  - send_clipboard: send text or the PC's current clipboard to the iPhone
  - read_clipboard: read the latest clipboard text sent from the iPhone (and copy to PC clipboard)
  - list_uploads: list files/photos shared from the iPhone to this computer
  - find_my_sound: play an alert sound on the iPhone to locate it (Find My iCloud + urgent push fallback)
  - find_my_status: check iPhone battery and location via Find My iCloud or iOS Shortcuts telemetry
  - icloud_mail_unread / icloud_mail_search / icloud_mail_send: read, search, and send Apple iCloud emails
  - open_qr_pairing: open the QR code overlay on the ULTRON HUD for instant iPhone pairing
"""
from __future__ import annotations

from pathlib import Path

from core import outcome
from plugins._iphone_core import (
    IPHONE_PLUGIN_SETTINGS,
    detect_local_iphone,
    find_my_iphone_action,
    icloud_mail_list,
    icloud_mail_send,
    load_iphone_state,
    send_push_notification,
    update_iphone_state,
)

PLUGIN_SETTINGS = IPHONE_PLUGIN_SETTINGS

PLUGIN = {
    "name": "iphone_control",
    "tier": "core",
    "brief": "Connect with Gabriel's iPhone: push notifications, Siri/Shortcuts telemetry, clipboard/file sync, Find My, and iCloud Mail.",
    "description": (
        "Integra o ULTRON ao iPhone e à conta Apple/iCloud de Gabriel: consultar estado, bateria e "
        "conexão do iPhone (status, find_my_status), enviar notificação, texto ou link para a tela "
        "do iPhone (notify), sincronizar área de transferência entre PC e iPhone (send_clipboard, "
        "read_clipboard), listar fotos/arquivos recebidos do iPhone (list_uploads), tocar alerta sonoro "
        "para encontrar o iPhone (find_my_sound), ler/enviar e-mails do iCloud (icloud_mail_unread, "
        "icloud_mail_search, icloud_mail_send) e exibir o QR Code de pareamento no HUD (open_qr_pairing)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "status",
                    "notify",
                    "send_clipboard",
                    "read_clipboard",
                    "list_uploads",
                    "find_my_sound",
                    "find_my_status",
                    "icloud_mail_unread",
                    "icloud_mail_search",
                    "icloud_mail_send",
                    "open_qr_pairing",
                ],
                "description": "Ação a executar na integração com o iPhone / iCloud.",
            },
            "title": {
                "type": "STRING",
                "description": "Título da notificação push (notify) ou assunto do e-mail iCloud (icloud_mail_send).",
            },
            "message": {
                "type": "STRING",
                "description": "Texto da notificação (notify), texto para área de transferência (send_clipboard) ou corpo do e-mail (icloud_mail_send).",
            },
            "url": {
                "type": "STRING",
                "description": "URL opcional para abrir no iPhone ao tocar na notificação.",
            },
            "priority": {
                "type": "STRING",
                "enum": ["low", "default", "high", "urgent"],
                "description": "Prioridade da notificação no iPhone (padrão 'default').",
            },
            "to": {
                "type": "STRING",
                "description": "Destinatário de e-mail para 'icloud_mail_send'.",
            },
            "query": {
                "type": "STRING",
                "description": "Termo de busca para 'icloud_mail_search'.",
            },
        },
        "required": ["action"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()

    try:
        if action == "status":
            info = detect_local_iphone()
            tel = info.get("last_telemetry") or {}
            return outcome.done(
                "iphone_status",
                device=info.get("configured_name", "iPhone"),
                lan_online=info.get("lan_reachable", False),
                usb_connected=info.get("usb_connected", False),
                bluetooth_paired=info.get("bluetooth_paired", False),
                battery=f"{tel['battery']}%" if tel.get("battery") is not None else "sem leitura recente",
                charging=tel.get("charging"),
                focus_mode=tel.get("focus_mode"),
                last_seen=tel.get("last_updated"),
                dashboard_url=info.get("dashboard_url"),
                shortcut_webhook=info.get("shortcut_webhook_url"),
                ntfy_topic=info.get("ntfy_topic"),
            )

        if action == "notify":
            title = str(params.get("title") or "ULTRON").strip()
            msg = str(params.get("message") or params.get("query") or "").strip()
            url = str(params.get("url") or "").strip()
            prio = str(params.get("priority") or "default").strip().lower()
            if not msg and not url:
                return outcome.failed("iphone_notify", "Informe 'message' (ou 'url') para enviar ao iPhone.")
            ok, details = send_push_notification(title=title, message=msg or url, url=url, priority=prio)
            if ok:
                return outcome.done("iphone_notify", title=title, details=details)
            return outcome.failed("iphone_notify", details)

        if action == "send_clipboard":
            text = str(params.get("message") or params.get("query") or "").strip()
            if not text:
                try:
                    import pyperclip
                    text = (pyperclip.paste() or "").strip()
                except Exception:
                    text = ""
            if not text:
                return outcome.failed("iphone_send_clipboard", "Nenhum texto informado e a área de transferência do PC está vazia.")
            update_iphone_state({"pc_to_iphone_clipboard": text})
            ok, push_msg = send_push_notification(
                title="Área de Transferência do ULTRON",
                message=text[:1500],
                priority="default",
            )
            return outcome.done(
                "iphone_send_clipboard",
                chars=len(text),
                pushed_to_iphone=ok,
                details=push_msg,
            )

        if action == "read_clipboard":
            state = load_iphone_state()
            clip = str(state.get("iphone_clipboard") or "").strip()
            if not clip:
                return outcome.failed(
                    "iphone_read_clipboard",
                    "Nenhum texto recebido recentemente da área de transferência do iPhone.",
                )
            copied_local = False
            try:
                import pyperclip
                pyperclip.copy(clip)
                copied_local = True
            except Exception:
                pass
            return (
                outcome.done("iphone_read_clipboard", copied_to_pc=copied_local, last_updated=state.get("last_updated"))
                + "\n"
                + outcome.untrusted("iphone_clipboard", clip[:4000])
            )

        if action == "list_uploads":
            from dashboard.server import UPLOADS_DIR
            files = []
            if UPLOADS_DIR.is_dir():
                for f in sorted((p for p in UPLOADS_DIR.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
                    files.append(f"- {f.name} ({round(f.stat().st_size / 1024, 1)} KB) em {f}")
            if not files:
                return outcome.done("iphone_uploads", count=0, folder=str(UPLOADS_DIR), summary="Nenhum arquivo recebido do iPhone ainda.")
            return outcome.done("iphone_uploads", count=len(files), folder=str(UPLOADS_DIR)) + "\n" + "\n".join(files)

        if action == "find_my_sound":
            ok, msg = find_my_iphone_action(play_sound=True)
            if ok:
                return outcome.done("iphone_find_my_sound", method="icloud_find_my", details=msg)
            # Also send an urgent push alert so the iPhone rings via notification even if pyicloud isn't configured
            ok_push, push_msg = send_push_notification(
                title="ALERTA DE LOCALIZAÇÃO ULTRON",
                message="Gabriel solicitou localizar este iPhone pelo ULTRON.",
                priority="urgent",
            )
            if ok_push:
                return outcome.done(
                    "iphone_find_my_sound",
                    method="urgent_push_notification",
                    details=f"{push_msg} (Nota Find My iCloud: {msg})",
                )
            return outcome.failed("iphone_find_my_sound", msg)

        if action == "find_my_status":
            ok, msg = find_my_iphone_action(play_sound=False)
            if ok:
                return outcome.done("iphone_find_my_status", source="icloud_find_my", details=msg)
            state = load_iphone_state()
            if state.get("battery") is not None or state.get("location"):
                return outcome.done(
                    "iphone_find_my_status",
                    source="ios_shortcut_telemetry",
                    battery=f"{state.get('battery')}%",
                    charging=state.get("charging"),
                    location=state.get("location") or "não informada",
                    last_updated=state.get("last_updated"),
                )
            return outcome.failed("iphone_find_my_status", msg)

        if action in ("icloud_mail_unread", "icloud_mail_search"):
            q = str(params.get("query") or "").strip() if action == "icloud_mail_search" else ""
            ok, res = icloud_mail_list(unseen_only=(action == "icloud_mail_unread"), search_query=q)
            if not ok:
                return outcome.failed(action, res)
            return outcome.done(action) + "\n" + outcome.untrusted("icloud_mail", res)

        if action == "icloud_mail_send":
            to = str(params.get("to") or "").strip()
            subj = str(params.get("title") or "Mensagem do ULTRON").strip()
            body = str(params.get("message") or "").strip()
            if not to or not body:
                return outcome.failed("icloud_mail_send", "Informe 'to' (destinatário) e 'message' (corpo do e-mail).")
            ok, res = icloud_mail_send(to=to, subject=subj, body=body)
            if ok:
                return outcome.done("icloud_mail_send", to=to, subject=subj, details=res)
            return outcome.failed("icloud_mail_send", res)

        if action == "open_qr_pairing":
            if player is not None and hasattr(player, "on_remote_clicked") and callable(player.on_remote_clicked):
                player.on_remote_clicked()
                return outcome.done("iphone_open_qr", details="QR Code de conexão com o iPhone exibido na tela do ULTRON.")
            info = detect_local_iphone()
            return outcome.done(
                "iphone_open_qr",
                dashboard_url=info.get("dashboard_url"),
                details="Clique no botão 'REMOTE' na janela do ULTRON para exibir o QR Code na tela.",
            )

        return outcome.failed("iphone_control", f"Ação desconhecida: {action}")
    except Exception as exc:
        return outcome.failed("iphone_control", f"Erro na integração com o iPhone ({action}): {exc}")

