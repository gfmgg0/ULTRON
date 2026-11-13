"""
Shared iPhone / iOS / iCloud integration layer for ULTRON.

Prefixed with '_' so `core.plugin_loader` treats this file as a shared helper
module rather than a standalone tool. Imported by `plugins/iphone_control.py`
and `dashboard/server.py`.

Features:
  1. iOS Shortcuts & Siri Bridge (persistent API key + telemetry/clipboard state in
     `config/integrations/iphone_state.json`).
  2. Push Notifications from ULTRON -> iPhone via ntfy.sh (zero-config topic),
     Bark, or Pushcut.
  3. Apple iCloud Mail (IMAP `imap.mail.me.com` / SMTP `smtp.mail.me.com`) via
     Apple ID + App-Specific Password.
  4. Apple Find My iPhone (`pyicloud` when installed) — battery, location, and
     play-sound to locate the iPhone.
  5. Local network (Wi-Fi ping/TCP), Bluetooth, and USB (`lsusb`/`ideviceinfo`)
     iPhone detection.
"""
from __future__ import annotations

import datetime as _dt
import email
import imaplib
import json
import os
import re
import secrets
import smtplib
import socket
import subprocess
from email.header import decode_header
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional, Tuple

import httpx

from memory.config_manager import get_plugin_config, save_plugin_config

ROOT = Path(__file__).resolve().parent.parent
INTEGRATIONS_DIR = ROOT / "config" / "integrations"
STATE_FILE = INTEGRATIONS_DIR / "iphone_state.json"

NAMESPACE = "iphone_ecosystem"


def ensure_integrations_dir() -> Path:
    INTEGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return INTEGRATIONS_DIR


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_settings(override: Optional[dict] = None) -> dict:
    stored = get_plugin_config(NAMESPACE)
    changed = False
    if not stored.get("shortcut_key"):
        stored["shortcut_key"] = "ULTRON-" + secrets.token_hex(4).upper()
        changed = True
    if not stored.get("ntfy_topic"):
        stored["ntfy_topic"] = "ultron-gabriel-" + secrets.token_hex(4).lower()
        changed = True
    if changed:
        try:
            save_plugin_config(NAMESPACE, stored)
        except Exception:
            pass
    if override and isinstance(override, dict):
        stored.update(override)
    return {
        "iphone_name": str(stored.get("iphone_name") or "iPhone de Gabriel").strip(),
        "iphone_ip": str(stored.get("iphone_ip") or "").strip(),
        "shortcut_key": str(stored.get("shortcut_key") or "").strip(),
        "push_provider": str(stored.get("push_provider") or "ntfy").strip().lower(),
        "ntfy_topic": str(stored.get("ntfy_topic") or "").strip(),
        "ntfy_server": str(stored.get("ntfy_server") or "https://ntfy.sh").strip().rstrip("/"),
        "bark_url": str(stored.get("bark_url") or "").strip(),
        "pushcut_secret": str(stored.get("pushcut_secret") or "").strip(),
        "apple_id": str(stored.get("apple_id") or "").strip(),
        "app_password": str(stored.get("app_password") or "").strip(),
    }


def load_iphone_state() -> dict[str, Any]:
    ensure_integrations_dir()
    if not STATE_FILE.is_file():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def update_iphone_state(patch: dict[str, Any]) -> dict[str, Any]:
    ensure_integrations_dir()
    state = load_iphone_state()
    state.update({k: v for k, v in (patch or {}).items() if v is not None})
    state["last_updated"] = _dt.datetime.now().isoformat(timespec="seconds")
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        os.chmod(STATE_FILE, 0o600)
    except Exception:
        pass
    return state


def verify_shortcut_key(provided_key: str) -> bool:
    cfg = get_settings()
    expected = cfg.get("shortcut_key", "")
    return bool(expected and provided_key and secrets.compare_digest(expected.strip(), provided_key.strip()))


# ── Push Notifications (ULTRON -> iPhone) ─────────────────────────────────────
def send_push_notification(
    title: str,
    message: str,
    url: str = "",
    priority: str = "default",
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    cfg = get_settings(settings_override)
    provider = cfg["push_provider"]

    try:
        if provider == "bark" and cfg["bark_url"]:
            base = cfg["bark_url"].rstrip("/")
            payload: dict[str, Any] = {"title": title, "body": message}
            if url:
                payload["url"] = url
            resp = httpx.post(base, json=payload, timeout=10.0)
            resp.raise_for_status()
            return True, f"Notificação enviada ao iPhone via Bark ({title})."

        if provider == "pushcut" and cfg["pushcut_secret"]:
            endpoint = f"https://api.pushcut.io/{cfg['pushcut_secret']}/notifications/ULTRON"
            payload = {"title": title, "text": message}
            if url:
                payload["defaultAction"] = {"url": url}
            resp = httpx.post(endpoint, json=payload, timeout=10.0)
            resp.raise_for_status()
            return True, f"Notificação enviada ao iPhone via Pushcut ({title})."

        # Default: ntfy.sh (works with the official 'ntfy' iOS app, no signup needed)
        topic = cfg["ntfy_topic"]
        if not topic:
            return False, "Tópico ntfy não configurado."
        endpoint = f"{cfg['ntfy_server']}/{topic}"
        headers = {
            "Title": title[:120],
            "Priority": priority if priority in ("min", "low", "default", "high", "urgent") else "default",
            "Tags": "iphone,robot",
        }
        if url:
            headers["Click"] = url
        resp = httpx.post(endpoint, content=message.encode("utf-8"), headers=headers, timeout=10.0)
        resp.raise_for_status()
        return True, f"Notificação enviada para o iPhone no tópico ntfy '{topic}'."
    except Exception as exc:
        return False, f"Falha ao enviar notificação push ao iPhone: {exc}"


# ── Local Network / USB / Bluetooth Detection ─────────────────────────────────
def detect_local_iphone(settings_override: Optional[dict] = None) -> dict[str, Any]:
    cfg = get_settings(settings_override)
    state = load_iphone_state()
    ip = cfg["iphone_ip"] or state.get("client_ip", "")
    info: dict[str, Any] = {
        "configured_name": cfg["iphone_name"],
        "iphone_ip": ip or "não definido",
        "lan_reachable": False,
        "usb_connected": False,
        "bluetooth_paired": False,
        "dashboard_url": f"http://{_local_ip()}:8000",
        "shortcut_webhook_url": f"http://{_local_ip()}:8000/api/iphone/shortcut",
        "shortcut_key": cfg["shortcut_key"],
        "ntfy_topic": cfg["ntfy_topic"],
    }

    if ip:
        try:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "1", ip],
                capture_output=True,
                text=True,
                timeout=3,
            )
            info["lan_reachable"] = r.returncode == 0
        except Exception:
            pass

    # Check USB connection via lsusb
    try:
        r = subprocess.run(["lsusb"], capture_output=True, text=True, timeout=3)
        out = (r.stdout or "").lower()
        if "apple" in out and ("iphone" in out or "ipad" in out or "05ac:" in out):
            info["usb_connected"] = True
    except Exception:
        pass

    # Check Bluetooth paired devices
    try:
        r = subprocess.run(["bluetoothctl", "devices"], capture_output=True, text=True, timeout=3)
        out = (r.stdout or "").lower()
        if "iphone" in out:
            info["bluetooth_paired"] = True
    except Exception:
        pass

    if state:
        info["last_telemetry"] = {
            "battery": state.get("battery"),
            "charging": state.get("charging"),
            "wifi": state.get("wifi"),
            "focus_mode": state.get("focus_mode"),
            "location": state.get("location"),
            "last_updated": state.get("last_updated"),
        }
    return info


# ── Apple iCloud Mail (IMAP / SMTP) ───────────────────────────────────────────
def _decode_mime_words(raw: str) -> str:
    if not raw:
        return ""
    parts = decode_header(raw)
    out: list[str] = []
    for content, enc in parts:
        if isinstance(content, bytes):
            out.append(content.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(str(content))
    return "".join(out).strip()


def icloud_mail_list(
    unseen_only: bool = True,
    search_query: str = "",
    max_results: int = 8,
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    cfg = get_settings(settings_override)
    user = cfg["apple_id"]
    pwd = cfg["app_password"].replace(" ", "")
    if not user or not pwd:
        return (
            False,
            "Apple ID e Senha de App (App-Specific Password) não configurados em ⚙ → PLUGIN SETTINGS (seção IPHONE & APPLE ICLOUD).",
        )

    try:
        with imaplib.IMAP4_SSL("imap.mail.me.com", 993) as imap:
            imap.login(user, pwd)
            imap.select("INBOX", readonly=True)
            if search_query:
                typ, data = imap.search("UTF-8", f'(OR SUBJECT "{search_query}" FROM "{search_query}")')
            elif unseen_only:
                typ, data = imap.search(None, "UNSEEN")
            else:
                typ, data = imap.search(None, "ALL")

            if typ != "OK" or not data or not data[0]:
                return True, "Nenhum e-mail encontrado no iCloud Mail."

            ids = data[0].split()[-max_results:]
            lines: list[str] = []
            for mid in reversed(ids):
                _, msg_data = imap.fetch(mid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                if not msg_data or not isinstance(msg_data[0], tuple):
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                frm = _decode_mime_words(msg.get("From", ""))
                subj = _decode_mime_words(msg.get("Subject", "(Sem assunto)"))
                dt = msg.get("Date", "")
                lines.append(f"- ID={mid.decode()} | De: {frm} | Assunto: {subj} | Data: {dt}")
            return True, "\n".join(lines) if lines else "Nenhum e-mail encontrado no iCloud Mail."
    except Exception as exc:
        return False, f"Erro ao acessar iCloud Mail (IMAP): {exc}"


def icloud_mail_send(
    to: str,
    subject: str,
    body: str,
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    cfg = get_settings(settings_override)
    user = cfg["apple_id"]
    pwd = cfg["app_password"].replace(" ", "")
    if not user or not pwd:
        return (
            False,
            "Apple ID e Senha de App (App-Specific Password) não configurados em ⚙ → PLUGIN SETTINGS.",
        )
    try:
        msg = EmailMessage()
        msg["From"] = user
        msg["To"] = to.strip()
        msg["Subject"] = subject.strip()
        msg.set_content(body or "")
        with smtplib.SMTP("smtp.mail.me.com", 587, timeout=15) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(user, pwd)
            smtp.send_message(msg)
        return True, f"E-mail enviado via iCloud Mail para {to}."
    except Exception as exc:
        return False, f"Erro ao enviar e-mail via iCloud Mail (SMTP): {exc}"


# ── Find My iPhone (via pyicloud when available) ──────────────────────────────
def find_my_iphone_action(
    play_sound: bool = False,
    lost_mode_phone: str = "",
    lost_mode_message: str = "",
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    cfg = get_settings(settings_override)
    user = cfg["apple_id"]
    pwd = cfg["app_password"]
    if not user or not pwd:
        return (
            False,
            "Informe seu Apple ID e senha em ⚙ → PLUGIN SETTINGS para usar o Buscar Meu iPhone (Find My).",
        )
    try:
        from pyicloud import PyiCloudService  # type: ignore
    except ImportError:
        return (
            False,
            "Pacote opcional 'pyicloud' não instalado para Buscar Meu iPhone direto via API Apple. "
            "Você pode instalar com 'pip install pyicloud' ou usar a notificação push / atalho iOS já configurado.",
        )

    try:
        api = PyiCloudService(user, pwd)
        if api.requires_2fa:
            return (
                False,
                "Sua conta Apple solicitou código 2FA para o Find My. Autentique a sessão pyicloud no terminal com 'icloud --username="
                f"{user}'.",
            )
        devices = list(api.devices)
        if not devices:
            return False, "Nenhum dispositivo encontrado no Buscar (Find My) desta conta Apple."

        target = devices[0]
        for d in devices:
            st = d.status()
            if "iphone" in str(st.get("deviceDisplayName", "")).lower() or "iphone" in str(st.get("name", "")).lower():
                target = d
                break

        status = target.status(["batteryLevel", "deviceStatus", "name"])
        loc = target.location() or {}
        if play_sound:
            target.play_sound()
            return True, f" Alerta sonoro disparado no '{status.get('name', 'iPhone')}' (Bateria: {round(float(status.get('batteryLevel') or 0)*100)}%)."
        if lost_mode_phone:
            target.lost_device(lost_mode_phone, lost_mode_message or "Este iPhone pertence a Gabriel. Por favor entre em contato.")
            return True, f"Modo Perdido ativado no '{status.get('name', 'iPhone')}'."

        bat = round(float(status.get("batteryLevel") or 0) * 100)
        lat = loc.get("latitude")
        lon = loc.get("longitude")
        loc_str = f"Lat={lat}, Lon={lon}" if lat and lon else "localização indisponível no momento"
        return True, f"Dispositivo: {status.get('name', 'iPhone')} | Bateria: {bat}% | Localização: {loc_str}"
    except Exception as exc:
        return False, f"Erro na API Find My iPhone: {exc}"


def test_iphone_connection_ui(values: dict) -> Tuple[bool, str]:
    """Callback for the 'TESTAR / NOTIFICAR IPHONE' button in PluginSettingsOverlay."""
    info = detect_local_iphone(settings_override=values)
    ok_push, push_msg = send_push_notification(
        title="ULTRON Conectado",
        message=f"Integração com {info['configured_name']} ativa! Painel: {info['dashboard_url']}",
        url=info["dashboard_url"],
        settings_override=values,
    )
    parts = [
        f"Webhook Siri/Atalhos: {info['shortcut_webhook_url']} (Key: {info['shortcut_key']})",
        f"Push: {push_msg}",
    ]
    if info["lan_reachable"]:
        parts.append(f"Wi-Fi LAN ({info['iphone_ip']}): Online")
    return ok_push or info["lan_reachable"], " | ".join(parts)


IPHONE_PLUGIN_SETTINGS = {
    "namespace": NAMESPACE,
    "title": "IPHONE & APPLE ICLOUD (SIRI · ATALHOS IOS · NOTIFICAÇÕES PUSH · ICLOUD MAIL · FIND MY)",
    "fields": [
        {
            "key": "iphone_name",
            "label": "Nome do iPhone",
            "type": "text",
            "default": "iPhone de Gabriel",
            "placeholder": "iPhone de Gabriel",
        },
        {
            "key": "iphone_ip",
            "label": "IP do iPhone na Rede Wi-Fi Local (opcional, para detecção de presença)",
            "type": "text",
            "default": "",
            "placeholder": "Ex.: 192.168.1.50",
        },
        {
            "key": "shortcut_key",
            "label": "Chave da API para Atalhos do iOS / Siri (X-Ultron-Key)",
            "type": "text",
            "default": "",
            "placeholder": "Gerada automaticamente (ex.: ULTRON-A1B2C3D4)",
        },
        {
            "key": "push_provider",
            "label": "Serviço de Notificação Push para o iPhone",
            "type": "choice",
            "options": ["ntfy", "bark", "pushcut"],
            "default": "ntfy",
        },
        {
            "key": "ntfy_topic",
            "label": "Tópico ntfy (assine este tópico no app 'ntfy' na App Store do iPhone)",
            "type": "text",
            "default": "",
            "placeholder": "ultron-gabriel-xxxx",
        },
        {
            "key": "bark_url",
            "label": "URL do app Bark no iPhone (opcional, se usar Bark)",
            "type": "text",
            "default": "",
            "placeholder": "https://api.day.app/SUA_CHAVE_BARK",
        },
        {
            "key": "apple_id",
            "label": "Apple ID / E-mail iCloud (opcional, para iCloud Mail e Buscar iPhone)",
            "type": "text",
            "default": "",
            "placeholder": "seu_email@icloud.com",
        },
        {
            "key": "app_password",
            "label": "Senha de App da Apple (App-Specific Password gerada em appleid.apple.com)",
            "type": "password",
            "default": "",
            "placeholder": "xxxx-xxxx-xxxx-xxxx",
        },
    ],
    "action": {
        "label": "▸  TESTAR CONEXÃO E ENVIAR NOTIFICAÇÃO AO IPHONE",
        "run": test_iphone_connection_ui,
    },
}

