"""
Shared Amazon Alexa integration layer for ULTRON (`plugins/_alexa_core.py`).

Prefixed with '_' so `core.plugin_loader` treats this file as a shared helper
module rather than a standalone tool. Imported by `plugins/alexa_control.py`
and `dashboard/server.py`.

Primary Integration (100% Native for Amazon Brasil `amazon.com.br` — NO third-party skills needed):
  1. Direct Amazon Alexa API (`alexa.amazon.com.br` / `pitangui.amazon.com`):
     - Uses local browser login (`authenticate_amazon_browser`) to save session
       cookies in `config/integrations/alexa_cookies.json`.
     - Discovers all Echo devices on the account (`/api/devices-v2/device`).
     - Speaks arbitrary TTS phrases in Portuguese on any Echo (`Alexa.Speak` and
       `AlexaAnnouncement` via `/api/behaviors/preview`).
     - Executes any natural-language command on Alexa (`Alexa.TextCommand`, e.g.,
       "apagar luz do quarto", "ligar ar condicionado", "tocar música") without
       needing any skill or routine setup!
     - Lists and triggers real Alexa Routines (`/api/behaviors/v2/automations`).
     - Adjusts Echo volume (`Alexa.DeviceControls.Volume`).

Optional Fallbacks:
  2. Home Assistant (`alexa_media` / scenes / scripts).
  3. Voice Monkey / Notify Me (if available).
  4. Incoming Alexa Webhook (`/api/alexa/webhook` and `/api/alexa/skill`).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import secrets
import shutil
import socket
from pathlib import Path
from typing import Any, Optional, Tuple

import httpx

from memory.config_manager import get_plugin_config, save_plugin_config

ROOT = Path(__file__).resolve().parent.parent
INTEGRATIONS_DIR = ROOT / "config" / "integrations"
STATE_FILE = INTEGRATIONS_DIR / "alexa_state.json"
COOKIES_FILE = INTEGRATIONS_DIR / "alexa_cookies.json"
DEVICES_FILE = INTEGRATIONS_DIR / "alexa_devices.json"
BROWSER_PROFILE_DIR = INTEGRATIONS_DIR / "alexa_browser_profile"

NAMESPACE = "alexa_ecosystem"

_AMAZON_DOMAINS = {
    "amazon.com.br": {
        "login_host": "www.amazon.com.br",
        "alexa_host": "alexa.amazon.com.br",
        "api_host": "pitangui.amazon.com",
        "locale": "pt-BR",
    },
    "amazon.com": {
        "login_host": "www.amazon.com",
        "alexa_host": "alexa.amazon.com",
        "api_host": "pitangui.amazon.com",
        "locale": "pt-BR",
    },
}

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def ensure_integrations_dir() -> Path:
    INTEGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return INTEGRATIONS_DIR


def _secure_chmod(path: Path) -> None:
    try:
        if path.exists():
            os.chmod(path, 0o600)
    except Exception:
        pass


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.AF_INET and socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_settings(override: Optional[dict] = None) -> dict:
    stored = get_plugin_config(NAMESPACE)
    if not stored.get("alexa_webhook_key"):
        stored["alexa_webhook_key"] = "ULTRON-ALEXA-" + secrets.token_hex(4).upper()
        try:
            save_plugin_config(NAMESPACE, stored)
        except Exception:
            pass
    if override and isinstance(override, dict):
        stored.update(override)
    domain = str(stored.get("amazon_domain") or "amazon.com.br").strip().lower()
    if domain not in _AMAZON_DOMAINS:
        domain = "amazon.com.br"
    return {
        "amazon_domain": domain,
        "default_echo_device": str(stored.get("default_echo_device") or "").strip(),
        "alexa_cookie_header": str(stored.get("alexa_cookie_header") or "").strip(),
        "alexa_webhook_key": str(stored.get("alexa_webhook_key") or "").strip(),
        "ha_url": str(stored.get("ha_url") or "").strip().rstrip("/"),
        "ha_token": str(stored.get("ha_token") or "").strip(),
        "ha_alexa_entity": str(stored.get("ha_alexa_entity") or "").strip(),
        "voicemonkey_token": str(stored.get("voicemonkey_token") or "").strip(),
        "voicemonkey_device": str(stored.get("voicemonkey_device") or "").strip(),
        "notify_me_code": str(stored.get("notify_me_code") or "").strip(),
    }


def load_alexa_state() -> dict[str, Any]:
    ensure_integrations_dir()
    if not STATE_FILE.is_file():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def update_alexa_state(patch: dict[str, Any]) -> dict[str, Any]:
    ensure_integrations_dir()
    state = load_alexa_state()
    state.update({k: v for k, v in (patch or {}).items() if v is not None})
    state["last_updated"] = _dt.datetime.now().isoformat(timespec="seconds")
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        _secure_chmod(STATE_FILE)
    except Exception:
        pass
    return state


def verify_alexa_key(provided_key: str) -> bool:
    cfg = get_settings()
    expected = cfg.get("alexa_webhook_key", "")
    return bool(expected and provided_key and secrets.compare_digest(expected.strip(), provided_key.strip()))


# ── Native Amazon Brasil Cookie & Session Management ──────────────────────────
def _parse_cookie_string(cookie_str: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in (cookie_str or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            k, v = k.strip(), v.strip()
            if k:
                out[k] = v
    return out


def load_saved_cookies(settings_override: Optional[dict] = None) -> dict[str, str]:
    ensure_integrations_dir()
    cfg = get_settings(settings_override)
    cookies: dict[str, str] = {}
    if COOKIES_FILE.is_file():
        try:
            raw = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cookies.update({str(k): str(v) for k, v in raw.items()})
            elif isinstance(raw, list):
                for c in raw:
                    if isinstance(c, dict) and c.get("name"):
                        cookies[str(c["name"])] = str(c.get("value", ""))
        except Exception:
            pass
    if cfg["alexa_cookie_header"]:
        cookies.update(_parse_cookie_string(cfg["alexa_cookie_header"]))
    return cookies


def save_cookies(cookies: dict[str, str]) -> None:
    ensure_integrations_dir()
    COOKIES_FILE.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")
    _secure_chmod(COOKIES_FILE)


def _ensure_csrf(client: httpx.Client, alexa_host: str, cookies: dict[str, str]) -> str:
    if "csrf" in cookies and cookies["csrf"]:
        return cookies["csrf"]
    for url in (
        f"https://{alexa_host}/api/language",
        "https://pitangui.amazon.com/api/language",
        f"https://{alexa_host}/api/devices-v2/device?cached=false",
    ):
        try:
            r = client.get(url, timeout=8.0)
            for k, v in r.cookies.items():
                cookies[k] = v
            if "csrf" in cookies and cookies["csrf"]:
                save_cookies(cookies)
                return cookies["csrf"]
        except Exception:
            continue
    return cookies.get("csrf", "")


def _build_alexa_client(settings_override: Optional[dict] = None) -> Tuple[Optional[httpx.Client], str, str]:
    cfg = get_settings(settings_override)
    dom_info = _AMAZON_DOMAINS[cfg["amazon_domain"]]
    alexa_host = dom_info["alexa_host"]
    cookies = load_saved_cookies(settings_override)
    if not cookies:
        return (
            None,
            alexa_host,
            "Conta Amazon ainda não conectada. Execute a ação 'authenticate' (ou clique em 'CONECTAR CONTA AMAZON BRASIL' em ⚙ → PLUGIN SETTINGS) para fazer login na sua conta Amazon.",
        )

    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
        "Referer": f"https://{alexa_host}/spa/index.html",
        "Origin": f"https://{alexa_host}",
    }
    transport = httpx.HTTPTransport(local_address="0.0.0.0")
    client = httpx.Client(
        cookies=cookies,
        headers=headers,
        follow_redirects=True,
        timeout=8.0,
        transport=transport,
    )
    csrf = _ensure_csrf(client, alexa_host, cookies)
    if csrf:
        client.headers["csrf"] = csrf
    return client, alexa_host, ""


def fetch_echo_devices(settings_override: Optional[dict] = None) -> Tuple[bool, list[dict[str, Any]], str]:
    """Fetch all Echo devices registered to the user's Amazon account."""
    client, alexa_host, err = _build_alexa_client(settings_override)
    if client is None:
        return False, [], err

    try:
        with client:
            for host in (alexa_host, "pitangui.amazon.com", "layla.amazon.com"):
                try:
                    resp = client.get(f"https://{host}/api/devices-v2/device?cached=false")
                    if resp.status_code == 200 and "devices" in resp.text:
                        data = resp.json()
                        devices = data.get("devices") or []
                        if devices:
                            DEVICES_FILE.write_text(json.dumps(devices, indent=2, ensure_ascii=False), encoding="utf-8")
                            _secure_chmod(DEVICES_FILE)
                            return True, devices, f"{len(devices)} dispositivo(s) encontrados na conta Amazon."
                except Exception:
                    continue
        return (
            False,
            [],
            "Sessão Amazon expirada ou não autorizada. Execute 'authenticate' para renovar o login na Amazon Brasil.",
        )
    except Exception as exc:
        return False, [], f"Erro ao consultar dispositivos Echo na Amazon: {exc}"


def _resolve_echo_device(target_name: str = "", settings_override: Optional[dict] = None) -> Tuple[Optional[dict[str, Any]], str]:
    cfg = get_settings(settings_override)
    wanted = (target_name or cfg["default_echo_device"] or "").strip().lower()

    devices: list[dict[str, Any]] = []
    if DEVICES_FILE.is_file():
        try:
            devices = json.loads(DEVICES_FILE.read_text(encoding="utf-8")) or []
        except Exception:
            devices = []
    if not devices:
        ok, devices, err = fetch_echo_devices(settings_override)
        if not ok or not devices:
            return None, err

    echo_candidates = [
        d for d in devices
        if d.get("deviceFamily") in ("ECHO", "ROOK", "KNIGHT", "WHA", "FIRE_TV", "TABLET")
        or "AUDIO_PLAYER" in (d.get("capabilities") or [])
    ] or devices

    if wanted:
        for d in echo_candidates:
            acc_name = str(d.get("accountName") or "").lower()
            serial = str(d.get("serialNumber") or "").lower()
            if wanted == acc_name or wanted == serial or wanted in acc_name:
                return d, ""

    for d in echo_candidates:
        if d.get("online") and d.get("deviceFamily") in ("ECHO", "ROOK", "KNIGHT"):
            return d, ""
    return echo_candidates[0], ""


def authenticate_amazon_browser(settings_override: Optional[dict] = None) -> Tuple[bool, str]:
    """
    Open a local Chrome/Playwright window to Amazon Brasil so the user can log in
    directly. Automatically captures the session cookies and discovers Echo devices.
    """
    ensure_integrations_dir()
    cfg = get_settings(settings_override)
    dom_info = _AMAZON_DOMAINS[cfg["amazon_domain"]]
    login_host = dom_info["login_host"]
    alexa_host = dom_info["alexa_host"]
    assoc = "brflex" if cfg["amazon_domain"] == "amazon.com.br" else "usflex"
    login_url = (
        f"https://{login_host}/ap/signin"
        f"?openid.pape.max_auth_age=0"
        f"&openid.return_to=https%3A%2F%2F{login_host}%2F%3Fref_%3Dnav_ya_signin"
        f"&openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
        f"&openid.assoc_handle={assoc}"
        f"&openid.mode=checkid_setup"
        f"&openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select"
        f"&openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0"
    )

    async def _run_auth() -> Tuple[bool, str]:
        from playwright.async_api import async_playwright

        BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        chrome_bin = (
            shutil.which("google-chrome")
            or shutil.which("google-chrome-stable")
            or shutil.which("chromium")
            or shutil.which("chromium-browser")
        )
        launch_kwargs: dict[str, Any] = {
            "user_data_dir": str(BROWSER_PROFILE_DIR),
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if chrome_bin:
            launch_kwargs["executable_path"] = chrome_bin

        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(**launch_kwargs)
            try:
                # Clear old auth tokens so we wait for a fresh login
                await ctx.clear_cookies()
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto(login_url, wait_until="domcontentloaded", timeout=30000)

                for _ in range(240):
                    if page.is_closed():
                        break
                    url_now = page.url
                    raw_cookies = await ctx.cookies()
                    cookie_map = {
                        c["name"]: c["value"]
                        for c in raw_cookies
                        if "amazon" in c.get("domain", "")
                    }
                    # Only real authenticated tokens (at-acbbr, sess-at-acbbr, at-main, sess-at-main)
                    has_auth_token = any(
                        k in ("at-acbbr", "sess-at-acbbr", "at-main", "sess-at-main") and bool(v)
                        for k, v in cookie_map.items()
                    )
                    in_auth_flow = any(
                        step in url_now
                        for step in ("/ap/signin", "/ap/mfa", "/ap/cvf", "/ap/challenge", "/ap/register")
                    )
                    if has_auth_token and not in_auth_flow:
                        # Fetch Alexa devices & CSRF inside the authenticated browser session
                        try:
                            await page.goto(
                                f"https://{alexa_host}/api/devices-v2/device?cached=false",
                                wait_until="domcontentloaded",
                                timeout=15000,
                            )
                            body_txt = await page.inner_text("body", timeout=3000)
                            if '"devices"' in body_txt:
                                parsed = json.loads(body_txt)
                                if isinstance(parsed.get("devices"), list):
                                    DEVICES_FILE.write_text(
                                        json.dumps(parsed["devices"], indent=2, ensure_ascii=False),
                                        encoding="utf-8",
                                    )
                                    _secure_chmod(DEVICES_FILE)
                        except Exception:
                            pass
                        raw_cookies = await ctx.cookies()
                        cookie_map = {
                            c["name"]: c["value"]
                            for c in raw_cookies
                            if "amazon" in c.get("domain", "")
                        }
                        save_cookies(cookie_map)
                        break
                    await asyncio.sleep(1.0)
            finally:
                try:
                    await ctx.close()
                except Exception:
                    pass

        ok, devs, _msg = fetch_echo_devices(settings_override)
        if ok:
            names = ", ".join(d.get("accountName", "Echo") for d in devs[:6])
            return True, f"Conta Amazon Brasil conectada com sucesso! Dispositivos Echo encontrados: {names}"
        return False, "A janela de login foi fechada antes de concluir a autenticação na Amazon."

    try:
        return asyncio.run(_run_auth())
    except Exception as exc:
        return False, f"Erro ao abrir navegador para login na Amazon: {exc}"


# ── Native Amazon Alexa Sequence Execution (Speak, TextCommand, Volume) ──────
def _execute_alexa_sequence(
    sequence_node: dict[str, Any],
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    client, alexa_host, err = _build_alexa_client(settings_override)
    if client is None:
        return False, err

    payload = {
        "behaviorId": "PREVIEW",
        "sequenceJson": json.dumps({
            "@type": "com.amazon.alexa.behaviors.model.Sequence",
            "startNode": sequence_node,
        }),
        "status": "ENABLED",
    }
    try:
        with client:
            for host in (alexa_host, "pitangui.amazon.com"):
                resp = client.post(
                    f"https://{host}/api/behaviors/preview",
                    json=payload,
                )
                if resp.status_code in (200, 201, 202):
                    return True, "Comando executado com sucesso na Amazon Alexa."
            return False, f"A API da Amazon retornou HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return False, f"Falha ao enviar comando para a Amazon Alexa: {exc}"


def alexa_speak(
    text: str,
    device: str = "",
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    """Make an Amazon Echo device speak `text` aloud in Portuguese."""
    cfg = get_settings(settings_override)
    msg = (text or "").strip()
    if not msg:
        return False, "Informe o texto que a Alexa deve falar."

    # 1. Native Amazon Brasil Account (Direct API — NO skills needed!)
    cookies = load_saved_cookies(settings_override)
    if cookies:
        dev, err = _resolve_echo_device(device, settings_override)
        if dev is None:
            return False, err
        node = {
            "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",
            "type": "Alexa.Speak",
            "operationPayload": {
                "deviceType": dev.get("deviceType"),
                "deviceSerialNumber": dev.get("serialNumber"),
                "locale": "pt-BR",
                "customerId": dev.get("deviceOwnerCustomerId"),
                "textToSpeak": msg,
            },
        }
        ok, details = _execute_alexa_sequence(node, settings_override)
        if ok:
            return True, f"Alexa falou no dispositivo '{dev.get('accountName', 'Echo')}': \"{msg}\""
        return False, details

    # 2. Home Assistant Alexa Media Player bridge
    if cfg["ha_url"] and cfg["ha_token"]:
        entity = (device or cfg["ha_alexa_entity"]).strip()
        headers = {
            "Authorization": f"Bearer {cfg['ha_token']}",
            "Content-Type": "application/json",
        }
        try:
            payload: dict[str, Any] = {"message": msg, "data": {"type": "announce"}}
            if entity:
                payload["target"] = [entity]
            resp = httpx.post(
                f"{cfg['ha_url']}/api/services/notify/alexa_media",
                headers=headers,
                json=payload,
                timeout=12.0,
            )
            resp.raise_for_status()
            return True, f"Anúncio enviado para a Alexa via Home Assistant ({entity or 'padrão'})."
        except Exception as exc:
            return False, f"Erro ao acionar Alexa via Home Assistant: {exc}"

    return (
        False,
        "Conta Amazon Brasil ainda não conectada. Peça ao ULTRON para 'autenticar conta da Alexa' (ou clique no botão 'CONECTAR CONTA AMAZON BRASIL' em ⚙ → PLUGIN SETTINGS) — não precisa de nenhuma skill!",
    )


def alexa_text_command(
    command_text: str,
    device: str = "",
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    """
    Send any natural-language voice command in Portuguese directly to Alexa
    (`Alexa.TextCommand`), exactly as if spoken to the Echo microphone!
    """
    cmd = (command_text or "").strip()
    if not cmd:
        return False, "Informe o comando que a Alexa deve executar."

    dev, err = _resolve_echo_device(device, settings_override)
    if dev is None:
        return False, err

    node = {
        "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",
        "type": "Alexa.TextCommand",
        "skillId": "amzn1.ask.1p.tellalexa",
        "operationPayload": {
            "deviceType": dev.get("deviceType"),
            "deviceSerialNumber": dev.get("serialNumber"),
            "locale": "pt-BR",
            "customerId": dev.get("deviceOwnerCustomerId"),
            "text": cmd,
        },
    }
    ok, details = _execute_alexa_sequence(node, settings_override)
    if ok:
        return True, f"Comando '{cmd}' executado pela Alexa no dispositivo '{dev.get('accountName', 'Echo')}'."
    return False, details


def alexa_set_volume(
    volume: int,
    device: str = "",
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    """Set volume (0-100) on an Echo device."""
    dev, err = _resolve_echo_device(device, settings_override)
    if dev is None:
        return False, err
    vol = max(0, min(100, int(volume)))
    node = {
        "@type": "com.amazon.alexa.behaviors.model.OpaquePayloadOperationNode",
        "type": "Alexa.DeviceControls.Volume",
        "operationPayload": {
            "deviceType": dev.get("deviceType"),
            "deviceSerialNumber": dev.get("serialNumber"),
            "locale": "pt-BR",
            "customerId": dev.get("deviceOwnerCustomerId"),
            "value": vol,
        },
    }
    ok, details = _execute_alexa_sequence(node, settings_override)
    if ok:
        return True, f"Volume do '{dev.get('accountName', 'Echo')}' ajustado para {vol}%."
    return False, details


def alexa_set_wake_word(
    wake_word: str = "ECHO",
    device: str = "",
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    """
    Change the physical wake word on an Echo device via Amazon Brasil API.
    Note: Amazon's Echo firmware chip supports ALEXA, ECHO, AMAZON, COMPUTER.
    For the wake word 'ULTRON' without saying 'Alexa', ULTRON uses its local
    Whisper 'Ultron' WakeWordDetector (`core/wake_word.py`) + Bluetooth audio
    routing to the Echo speaker!
    """
    dev, err = _resolve_echo_device(device, settings_override)
    if dev is None:
        return False, err
    w = (wake_word or "ECHO").strip().upper()
    if w not in ("ALEXA", "ECHO", "AMAZON", "COMPUTER"):
        return (
            False,
            f"O chip interno da Amazon só aceita ALEXA, ECHO, AMAZON ou COMPUTER no hardware do Echo. "
            f"A palavra de ativação 'ULTRON' já está ativa diretamente pelo detector de voz do ULTRON + saída Bluetooth no seu Echo!",
        )
    client, alexa_host, err = _build_alexa_client(settings_override)
    if client is None:
        return False, err
    payload = {
        "wakeWords": [
            {
                "active": True,
                "deviceSerialNumber": dev.get("serialNumber"),
                "deviceType": dev.get("deviceType"),
                "midFieldState": None,
                "wakeWord": w,
            }
        ]
    }
    try:
        with client:
            resp = client.put(f"https://{alexa_host}/api/wake-word", json=payload)
            if resp.status_code in (200, 202, 204):
                return True, f"Palavra de ativação física do '{dev.get('accountName', 'Echo')}' alterada para '{w}'."
            return False, f"A Amazon retornou HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as exc:
        return False, f"Erro ao alterar wake word do Echo: {exc}"


def alexa_list_routines(settings_override: Optional[dict] = None) -> Tuple[bool, list[dict[str, Any]], str]:
    """Fetch user's configured Alexa Routines from Amazon Brasil."""
    client, alexa_host, err = _build_alexa_client(settings_override)
    if client is None:
        return False, [], err
    try:
        with client:
            for host in (alexa_host, "pitangui.amazon.com"):
                resp = client.get(f"https://{host}/api/behaviors/v2/automations?limit=100")
                if resp.status_code == 200:
                    routines = resp.json()
                    if isinstance(routines, list):
                        return True, routines, f"{len(routines)} rotina(s) encontradas."
        return False, [], "Não foi possível listar as rotinas da conta Amazon."
    except Exception as exc:
        return False, [], f"Erro ao consultar rotinas da Alexa: {exc}"


def alexa_trigger_routine(
    routine_id_or_name: str,
    device: str = "",
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    """Trigger an Alexa Routine by name/utterance or fallback to `Alexa.TextCommand`."""
    rid = (routine_id_or_name or "").strip()
    if not rid:
        return False, "Informe o nome da rotina ou comando para a Alexa."

    cookies = load_saved_cookies(settings_override)
    if cookies:
        dev, err = _resolve_echo_device(device, settings_override)
        if dev is None:
            return False, err

        ok_r, routines, _ = alexa_list_routines(settings_override)
        if ok_r and routines:
            wanted = rid.lower()
            for r in routines:
                r_name = str(r.get("name") or "").lower()
                triggers = r.get("triggers") or []
                utterances = [
                    str((t.get("payload") or {}).get("utterance") or "").lower()
                    for t in triggers if isinstance(t, dict)
                ]
                if wanted == r_name or wanted in r_name or any(wanted == u or wanted in u for u in utterances if u):
                    seq = r.get("sequence")
                    if isinstance(seq, dict):
                        seq_str = json.dumps(seq)
                        seq_str = seq_str.replace("ALEXA_CURRENT_DEVICE_TYPE", str(dev.get("deviceType", "")))
                        seq_str = seq_str.replace("ALEXA_CURRENT_DSN", str(dev.get("serialNumber", "")))
                        client, alexa_host, _ = _build_alexa_client(settings_override)
                        if client:
                            with client:
                                resp = client.post(
                                    f"https://{alexa_host}/api/behaviors/preview",
                                    json={
                                        "behaviorId": r.get("automationId", "PREVIEW"),
                                        "sequenceJson": seq_str,
                                        "status": "ENABLED",
                                    },
                                )
                                if resp.status_code in (200, 201, 202):
                                    return True, f"Rotina '{r.get('name') or rid}' executada com sucesso na Alexa."

        # Fallback: execute directly via Alexa.TextCommand!
        return alexa_text_command(rid, device=device, settings_override=settings_override)

    return (
        False,
        "Conecte sua conta Amazon Brasil com a ação 'authenticate' (ou no botão em ⚙ → PLUGIN SETTINGS) para disparar rotinas e comandos na Alexa sem precisar de nenhuma skill.",
    )


# ── Bluetooth Speaker Bridge (Voz Original do ULTRON 'Algenib' no Echo) ──────
def get_bluetooth_echo_status() -> dict[str, Any]:
    """Check whether an Amazon Echo is paired/connected via Bluetooth and active as PipeWire audio output."""
    import re as _re
    import subprocess as _sp

    paired_mac = ""
    paired_name = ""
    connected = False
    active_sink_id: Optional[int] = None
    is_default_sink = False

    try:
        r = _sp.run(["bluetoothctl", "devices"], capture_output=True, text=True, timeout=4)
        for line in r.stdout.splitlines():
            if "Echo" in line or "Amazon" in line:
                parts = line.split(" ", 2)
                if len(parts) >= 3:
                    paired_mac = parts[1].strip()
                    paired_name = parts[2].strip()
                    break
        if paired_mac:
            info = _sp.run(["bluetoothctl", "info", paired_mac], capture_output=True, text=True, timeout=4)
            connected = "Connected: yes" in info.stdout
    except Exception:
        pass

    try:
        wp = _sp.run(["wpctl", "status"], capture_output=True, text=True, timeout=4)
        in_sinks = False
        for line in wp.stdout.splitlines():
            if "Sinks:" in line:
                in_sinks = True
                continue
            if in_sinks and any(k in line for k in ("Sources:", "Filters:", "Streams:", "Video")):
                in_sinks = False
            if in_sinks and ("Echo" in line or "Amazon" in line):
                m = _re.search(r"(\d+)\.\s+(Echo[^\[]+|Amazon[^\[]+)", line)
                if m:
                    active_sink_id = int(m.group(1))
                    is_default_sink = "*" in line[: line.find(m.group(1))]
                    break
    except Exception:
        pass

    return {
        "paired_mac": paired_mac,
        "paired_name": paired_name,
        "bluetooth_connected": connected,
        "pipewire_sink_id": active_sink_id,
        "ultron_voice_on_echo": bool(connected and active_sink_id and is_default_sink),
    }


def alexa_connect_bluetooth_speaker(
    device: str = "",
    volume_pct: int = 85,
    settings_override: Optional[dict] = None,
) -> Tuple[bool, str]:
    """
    Connect the PC to the Amazon Echo via Bluetooth and set it as the default
    PipeWire audio output sink so ULTRON's real voice ('Algenib' in Gemini Live)
    plays directly through the Echo speaker!
    """
    import subprocess as _sp
    import time as _time

    bt = get_bluetooth_echo_status()
    mac = bt.get("paired_mac", "")
    name = bt.get("paired_name") or "Echo"

    if not mac:
        # Ask Alexa to enter Bluetooth connect/pair mode first
        alexa_text_command("conectar bluetooth", device=device, settings_override=settings_override)
        return (
            False,
            "Nenhum Echo pareado no Bluetooth do Linux ainda. Diga 'Alexa, parear Bluetooth' e pareie o Echo nas configurações Bluetooth do sistema.",
        )

    if not bt.get("bluetooth_connected"):
        try:
            alexa_text_command("conectar bluetooth", device=device or name, settings_override=settings_override)
        except Exception:
            pass
        try:
            _sp.run(["bluetoothctl", "connect", mac], capture_output=True, text=True, timeout=10)
        except Exception as exc:
            return False, f"Erro ao conectar Bluetooth com {name} ({mac}): {exc}"

    # Wait briefly for PipeWire bluez5 sink to register
    sink_id: Optional[int] = None
    for _ in range(12):
        st = get_bluetooth_echo_status()
        sink_id = st.get("pipewire_sink_id")
        if sink_id:
            break
        _time.sleep(0.35)

    if not sink_id:
        return False, f"Bluetooth conectado a {name} ({mac}), mas o sink de áudio PipeWire ainda não apareceu."

    vol_float = max(0.1, min(1.0, float(volume_pct) / 100.0))
    try:
        _sp.run(["wpctl", "set-default", str(sink_id)], check=False, timeout=4)
        _sp.run(["wpctl", "set-volume", str(sink_id), f"{vol_float:.2f}"], check=False, timeout=4)
    except Exception as exc:
        return False, f"Conectado ao Bluetooth {name}, mas falhou ao definir saída padrão no PipeWire: {exc}"

    update_alexa_state({"bluetooth_speaker_active": True, "bluetooth_echo_name": name, "bluetooth_mac": mac})
    return (
        True,
        f"Voz original do ULTRON (Algenib) agora está saindo diretamente na sua Alexa '{name}' ({mac}) via Bluetooth (Sink #{sink_id})!",
    )


def alexa_disconnect_bluetooth_speaker() -> Tuple[bool, str]:
    """Disconnect Echo Bluetooth audio so ULTRON's voice returns to the PC speaker."""
    import subprocess as _sp

    bt = get_bluetooth_echo_status()
    mac = bt.get("paired_mac", "")
    name = bt.get("paired_name") or "Echo"
    if not mac:
        return False, "Nenhum dispositivo Echo Bluetooth encontrado."
    try:
        _sp.run(["bluetoothctl", "disconnect", mac], capture_output=True, text=True, timeout=8)
        update_alexa_state({"bluetooth_speaker_active": False})
        return True, f"Áudio Bluetooth desconectado do '{name}'. A voz do ULTRON voltou para o alto-falante do PC."
    except Exception as exc:
        return False, f"Erro ao desconectar Bluetooth do '{name}': {exc}"


_LAST_VOICE_HISTORY_CACHE: list[dict[str, Any]] = []


# ── Echo Microphone → ULTRON Voice History Bridge (Zero Skills Needed!) ──────
def fetch_recent_voice_history(
    limit: int = 12,
    settings_override: Optional[dict] = None,
) -> list[dict[str, Any]]:
    """
    Fetch recent voice utterances spoken to any Echo on the user's Amazon Brasil
    account (`customer-history-records`).
    """
    global _LAST_VOICE_HISTORY_CACHE
    client, _alexa_host, _err = _build_alexa_client(settings_override)
    if client is None:
        return list(_LAST_VOICE_HISTORY_CACHE[:limit])
    url = "https://www.amazon.com.br/alexa-privacy/apd/rvh/customer-history-records?startTime=0&endTime=9999999999999"
    try:
        import time as _time
        with client:
            resp = None
            for _ in range(6):
                r = client.get(url, timeout=8.0)
                if r.status_code == 200 and r.text.strip().startswith("{"):
                    resp = r
                    break
                _time.sleep(0.25)
            if resp is None:
                return list(_LAST_VOICE_HISTORY_CACHE[:limit])
            data = resp.json()
            records = data.get("customerHistoryRecords") or []
            out: list[dict[str, Any]] = []
            for rec in records:
                if not isinstance(rec, dict):
                    continue
                items = rec.get("voiceHistoryRecordItems") or []
                transcript = ""
                alexa_reply = ""
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    itype = item.get("recordItemType")
                    txt = str(item.get("transcriptText") or "").strip()
                    if itype == "CUSTOMER_TRANSCRIPT" and txt and not transcript:
                        transcript = txt
                    elif itype == "ALEXA_RESPONSE" and txt and not alexa_reply:
                        alexa_reply = txt
                if transcript:
                    out.append({
                        "record_key": str(rec.get("recordKey") or ""),
                        "timestamp": int(rec.get("timestamp") or 0),
                        "device_name": str((rec.get("device") or {}).get("deviceName") or "Echo"),
                        "utterance_type": str(rec.get("utteranceType") or ""),
                        "transcript": transcript,
                        "alexa_response": alexa_reply,
                    })
                if len(out) >= limit:
                    break
            if out:
                _LAST_VOICE_HISTORY_CACHE = out
            return out
    except Exception:
        return list(_LAST_VOICE_HISTORY_CACHE[:limit])


def extract_ultron_voice_command(transcript: str) -> Optional[str]:
    """
    Given a raw Portuguese transcript spoken to an Echo microphone (e.g.,
    'ultron qual é a minha agenda de hoje' or 'pergunta pro ultron que horas são'),
    extract the command intended for ULTRON. Returns None if not addressed to ULTRON.
    """
    import re as _re

    raw = (transcript or "").strip()
    if not raw:
        return None
    low = raw.lower()
    # Strip leading wake word 'alexa' if present
    low = _re.sub(r"^alexa[\s,.:;-]*", "", low).strip()

    # Check if the user mentioned 'ultron' (or 'utron' / 'ultrão' common ASR variants)
    m = _re.search(
        r"\b(?:pergunta\s+pro\s+|pergunte\s+ao\s+|fale\s+com\s+o\s+|diga\s+ao\s+|manda\s+o\s+|modo\s+|ativar\s+)?(?:ultron|utron|ultrão|jarvis)\b[\s,.:;-]*(.*)$",
        low,
         flags=_re.IGNORECASE,
    )
    if not m:
        return None
    cmd = m.group(1).strip()
    if not cmd:
        return "Olá Ultron, estou falando com você pelo microfone da Alexa. Diga que está pronto na escuta."
    return cmd


def get_alexa_status(settings_override: Optional[dict] = None) -> dict[str, Any]:
    cfg = get_settings(settings_override)
    state = load_alexa_state()
    cookies = load_saved_cookies(settings_override)
    devices: list[dict[str, Any]] = []
    if DEVICES_FILE.is_file():
        try:
            devices = json.loads(DEVICES_FILE.read_text(encoding="utf-8")) or []
        except Exception:
            devices = []
    echo_names = [d.get("accountName", "") for d in devices if d.get("accountName")]
    bt = get_bluetooth_echo_status()
    ip = _local_ip()
    return {
        "amazon_brasil_connected": bool(cookies),
        "echo_devices": echo_names,
        "default_echo_device": cfg["default_echo_device"] or (echo_names[0] if echo_names else "auto"),
        "bluetooth_echo": bt,
        "echo_mic_bridge_enabled": True,
        "home_assistant_configured": bool(cfg["ha_url"] and cfg["ha_token"]),
        "skill_endpoint": f"http://{ip}:8000/api/alexa/skill",
        "webhook_endpoint": f"http://{ip}:8000/api/alexa/webhook",
        "webhook_key": cfg["alexa_webhook_key"],
        "last_command_from_alexa": state.get("last_command"),
        "last_updated": state.get("last_updated"),
    }


def test_or_connect_alexa_ui(values: dict) -> Tuple[bool, str]:
    cookies = load_saved_cookies(settings_override=values)
    if not cookies:
        return authenticate_amazon_browser(settings_override=values)
    ok, devs, msg = fetch_echo_devices(settings_override=values)
    if ok and devs:
        names = ", ".join(d.get("accountName", "Echo") for d in devs[:5])
        bt_ok, bt_msg = alexa_connect_bluetooth_speaker(settings_override=values)
        if bt_ok:
            return True, f"Conectado! Echos: {names} | {bt_msg}"
        ok_spk, spk_msg = alexa_speak(
            "Ultron conectado diretamente à sua conta Amazon Brasil, Chefe.",
            settings_override=values,
        )
        return True, f"Conectado! Echos: {names} | {spk_msg if ok_spk else msg}"
    return authenticate_amazon_browser(settings_override=values)


ALEXA_PLUGIN_SETTINGS = {
    "namespace": NAMESPACE,
    "title": "AMAZON ALEXA BRASIL (CONEXÃO DIRETA SEM SKILLS · ECHO TTS · CASA INTELIGENTE · ROTINAS)",
    "fields": [
        {
            "key": "amazon_domain",
            "label": "Domínio da Conta Amazon",
            "type": "choice",
            "options": ["amazon.com.br", "amazon.com"],
            "default": "amazon.com.br",
        },
        {
            "key": "default_echo_device",
            "label": "Nome do seu Echo Principal (opcional; deixe em branco para detectar automaticamente)",
            "type": "text",
            "default": "",
            "placeholder": "Ex.: Echo Dot de Gabriel ou Echo Sala",
        },
        {
            "key": "alexa_cookie_header",
            "label": "Cookie de Sessão Amazon (opcional — preenchido automaticamente pelo botão abaixo)",
            "type": "password",
            "default": "",
            "placeholder": "Clique no botão abaixo para abrir o login da Amazon Brasil",
        },
        {
            "key": "ha_url",
            "label": "URL do Home Assistant (opcional)",
            "type": "text",
            "default": "",
            "placeholder": "http://192.168.0.100:8123",
        },
        {
            "key": "ha_token",
            "label": "Token do Home Assistant (opcional)",
            "type": "password",
            "default": "",
            "placeholder": "eyJhbGciOiJIUzI1NiIs...",
        },
        {
            "key": "alexa_webhook_key",
            "label": "Chave de Segurança Webhook Alexa → ULTRON (X-Ultron-Key)",
            "type": "text",
            "default": "",
            "placeholder": "Gerada automaticamente",
        },
    ],
    "action": {
        "label": "▸  CONECTAR CONTA AMAZON BRASIL (SEM SKILLS) / TESTAR ECHO",
        "run": test_or_connect_alexa_ui,
    },
}
