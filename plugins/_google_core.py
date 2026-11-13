"""
Shared Google Ecosystem authentication & API service layer for ULTRON.

Prefixed with '_' so `core.plugin_loader` treats this file as a shared helper
module rather than a standalone tool. All Google plugins (`gmail_control`,
`calendar_control`, `google_drive_control`, `google_workspace_docs`,
`google_tasks_contacts`, `google_youtube_account`) import from here.

Supported authentication methods (tried in order):
  1. Cached OAuth 2.0 User Token (`config/integrations/google_token.json`),
     automatically refreshed when expired.
  2. Interactive OAuth 2.0 Desktop flow (`InstalledAppFlow`) using:
       - `config/integrations/google_credentials.json` (or custom path in settings), OR
       - `client_id` + `client_secret` configured in `⚙ → PLUGIN SETTINGS`, OR
       - any `client_secret*.json` found in `config/integrations/`, `config/`, or `~/Downloads`.
  3. Google Cloud CLI (`gcloud auth application-default print-access-token` / ADC)
     when available on the machine.
  4. Service Account JSON (`"type": "service_account"`) if configured in
     `credentials_path` (works for shared Drive, Sheets, Docs, Calendar).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional, Tuple
from zoneinfo import ZoneInfo

from memory.config_manager import get_plugin_config, save_plugin_config

ROOT = Path(__file__).resolve().parent.parent
INTEGRATIONS_DIR = ROOT / "config" / "integrations"
DEFAULT_CREDENTIALS_PATH = INTEGRATIONS_DIR / "google_credentials.json"
DEFAULT_TOKEN_PATH = INTEGRATIONS_DIR / "google_token.json"

NAMESPACE = "google_ecosystem"
DEFAULT_TIMEZONE = "America/Sao_Paulo"

# Comprehensive Google Ecosystem OAuth scopes
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/youtube",
]


def ensure_integrations_dir() -> Path:
    INTEGRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    return INTEGRATIONS_DIR


def _secure_chmod(path: Path) -> None:
    try:
        if path.exists():
            os.chmod(path, 0o600)
    except Exception:
        pass


def get_settings(override: Optional[dict] = None) -> dict:
    stored = get_plugin_config(NAMESPACE)
    if override and isinstance(override, dict):
        stored.update(override)
    return {
        "api_key": str(stored.get("api_key") or "").strip(),
        "credentials_path": str(stored.get("credentials_path") or DEFAULT_CREDENTIALS_PATH).strip(),
        "token_path": str(stored.get("token_path") or DEFAULT_TOKEN_PATH).strip(),
        "client_id": str(stored.get("client_id") or "").strip(),
        "client_secret": str(stored.get("client_secret") or "").strip(),
        "calendar_id": str(stored.get("calendar_id") or "primary").strip() or "primary",
        "timezone": str(stored.get("timezone") or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE,
        "auto_open_browser": bool(stored.get("auto_open_browser", True)),
    }


def get_tz(tz_name: Optional[str] = None) -> ZoneInfo:
    name = (tz_name or get_settings().get("timezone") or DEFAULT_TIMEZONE).strip()
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TIMEZONE)


def discover_credentials_file(custom_path: str = "") -> Optional[Path]:
    """Locate an OAuth Desktop or Service Account JSON file on disk."""
    candidates: list[Path] = []
    if custom_path:
        candidates.append(Path(custom_path).expanduser())
    candidates.extend([
        DEFAULT_CREDENTIALS_PATH,
        INTEGRATIONS_DIR / "credentials.json",
        ROOT / "config" / "credentials.json",
        ROOT / "credentials.json",
    ])
    for folder in (INTEGRATIONS_DIR, ROOT / "config", Path.home() / "Downloads", Path.home() / "Documentos", Path.home() / "Documents"):
        try:
            if folder.is_dir():
                for f in sorted(folder.glob("client_secret*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                    candidates.append(f)
                for f in sorted(folder.glob("*google*credentials*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
                    candidates.append(f)
        except Exception:
            pass

    for path in candidates:
        try:
            if path.is_file() and path.stat().st_size > 20:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and (
                    "installed" in data or "web" in data or data.get("type") in ("service_account", "authorized_user")
                ):
                    return path
        except Exception:
            continue
    return None


def import_credentials_file(source_path: str = "") -> Tuple[bool, str]:
    """Copy a credentials.json / client_secret*.json into config/integrations/google_credentials.json."""
    ensure_integrations_dir()
    src = discover_credentials_file(source_path)
    if src is None:
        return False, (
            "Nenhum arquivo client_secret*.json ou credentials.json válido foi encontrado. "
            "Baixe o OAuth Desktop Client JSON no Google Cloud Console ou informe o caminho completo."
        )
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
        cred_type = "OAuth Desktop/Web" if ("installed" in data or "web" in data) else data.get("type", "desconhecido")
        if src.resolve() != DEFAULT_CREDENTIALS_PATH.resolve():
            shutil.copy2(src, DEFAULT_CREDENTIALS_PATH)
            _secure_chmod(DEFAULT_CREDENTIALS_PATH)
        save_plugin_config(NAMESPACE, {"credentials_path": str(DEFAULT_CREDENTIALS_PATH)})
        return True, f"Credenciais ({cred_type}) importadas de '{src}' para '{DEFAULT_CREDENTIALS_PATH}'."
    except Exception as exc:
        return False, f"Falha ao importar credenciais: {exc}"


def _build_inline_client_config(client_id: str, client_secret: str) -> dict:
    return {
        "installed": {
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": ["http://localhost"],
        }
    }


def load_credentials(
    interactive: bool = False,
    settings_override: Optional[dict] = None,
) -> Tuple[Optional[Any], str, str]:
    """
    Returns (credentials, auth_mode, message).
    auth_mode is one of: 'oauth_user', 'service_account', 'adc', 'none'.
    """
    ensure_integrations_dir()
    cfg = get_settings(settings_override)
    token_path = Path(cfg["token_path"]).expanduser()

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials as UserCredentials
        from google.oauth2 import service_account
    except ImportError as exc:
        return None, "none", f"Bibliotecas Google Auth ausentes ({exc}). Execute: pip install google-api-python-client google-auth-oauthlib"

    # 1. Cached OAuth 2.0 user token
    if token_path.is_file():
        try:
            creds = UserCredentials.from_authorized_user_file(str(token_path))
            if creds and creds.valid:
                return creds, "oauth_user", "Autenticado via OAuth 2.0 (token ativo)."
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_path.write_text(creds.to_json(), encoding="utf-8")
                _secure_chmod(token_path)
                return creds, "oauth_user", "Autenticado via OAuth 2.0 (token renovado automaticamente)."
        except Exception as exc:
            print(f"[GoogleCore] Falha ao carregar/renovar token em {token_path}: {exc}")

    # 2. Check credentials file or inline client_id + client_secret
    cred_file = discover_credentials_file(cfg["credentials_path"])
    cred_data: Optional[dict] = None
    if cred_file and cred_file.is_file():
        try:
            cred_data = json.loads(cred_file.read_text(encoding="utf-8"))
        except Exception:
            cred_data = None

    # 2a. Authorized user JSON placed in credentials_path
    if isinstance(cred_data, dict) and cred_data.get("type") == "authorized_user":
        try:
            creds = UserCredentials.from_authorized_user_info(cred_data)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            _secure_chmod(token_path)
            return creds, "oauth_user", f"Autenticado via credenciais de usuário ({cred_file.name})."
        except Exception as exc:
            print(f"[GoogleCore] Falha ao usar authorized_user de {cred_file}: {exc}")

    # 2b. Interactive OAuth 2.0 Desktop flow (if requested or if OAuth client config is present and auto_open_browser is True)
    has_oauth_client = (
        (isinstance(cred_data, dict) and ("installed" in cred_data or "web" in cred_data))
        or (bool(cfg["client_id"]) and bool(cfg["client_secret"]))
    )
    if has_oauth_client and interactive:
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            if isinstance(cred_data, dict) and ("installed" in cred_data or "web" in cred_data):
                flow = InstalledAppFlow.from_client_config(cred_data, GOOGLE_SCOPES)
            else:
                client_cfg = _build_inline_client_config(cfg["client_id"], cfg["client_secret"])
                flow = InstalledAppFlow.from_client_config(client_cfg, GOOGLE_SCOPES)
            creds = flow.run_local_server(
                port=0,
                open_browser=cfg["auto_open_browser"],
                authorization_prompt_message="Abra o navegador para autorizar o ULTRON na sua Conta Google: {url}",
                success_message="ULTRON conectado com sucesso ao seu ecossistema Google! Você já pode fechar esta aba.",
            )
            token_path.write_text(creds.to_json(), encoding="utf-8")
            _secure_chmod(token_path)
            return creds, "oauth_user", "Conta Google conectada via OAuth 2.0 com sucesso."
        except Exception as exc:
            return None, "none", f"Falha no fluxo de login OAuth 2.0: {exc}"

    # 3. Service Account JSON (works right away for Drive, Sheets, Docs, Calendar shared with the service account)
    if isinstance(cred_data, dict) and cred_data.get("type") == "service_account":
        try:
            sa_scopes = [s for s in GOOGLE_SCOPES if s != "openid"]
            creds = service_account.Credentials.from_service_account_info(cred_data, scopes=sa_scopes)
            sa_email = cred_data.get("client_email", "service-account")
            return creds, "service_account", f"Autenticado via Service Account ({sa_email} em {cred_file.name})."
        except Exception as exc:
            print(f"[GoogleCore] Falha ao carregar Service Account: {exc}")

    # 4. Application Default Credentials (ADC) fallback
    try:
        import google.auth
        creds, _proj = google.auth.default(scopes=GOOGLE_SCOPES)
        if creds:
            if not creds.valid and getattr(creds, "refresh_token", None):
                creds.refresh(Request())
            if creds.valid:
                return creds, "adc", "Autenticado via Google Application Default Credentials (ADC)."
    except Exception:
        pass

    if has_oauth_client:
        return (
            None,
            "none",
            "Cliente OAuth encontrado, mas o login ainda não foi concluído. "
            "Peça ao ULTRON para 'autenticar conta Google' ou clique em 'CONECTAR / VERIFICAR CONTA GOOGLE' em ⚙ → PLUGIN SETTINGS.",
        )

    return (
        None,
        "none",
        "Credenciais OAuth Google não configuradas. Coloque seu arquivo 'google_credentials.json' (OAuth Desktop Client) "
        f"em '{DEFAULT_CREDENTIALS_PATH}' ou informe Client ID e Client Secret em ⚙ → PLUGIN SETTINGS.",
    )


def get_service(
    service_name: str,
    version: str,
    interactive_fallback: bool = False,
    require_user_oauth: bool = False,
) -> Tuple[Optional[Any], str, str]:
    """
    Build a Google API client (`googleapiclient.discovery.build`).
    Returns `(service, auth_mode, error_or_status_message)`.
    """
    creds, mode, msg = load_credentials(interactive=interactive_fallback)
    if creds is None:
        return None, mode, msg

    if require_user_oauth and mode == "service_account":
        return (
            None,
            mode,
            f"O serviço '{service_name}' pessoal (como caixa de entrada Gmail ou conta pessoal YouTube) "
            "requer login OAuth 2.0 de usuário (atualmente apenas uma Service Account está ativa). "
            f"Salve seu OAuth Desktop Client JSON em '{DEFAULT_CREDENTIALS_PATH}' (ou preencha Client ID e Client Secret em ⚙ → PLUGIN SETTINGS) "
            "e execute a ação 'authenticate'.",
        )

    try:
        from googleapiclient.discovery import build
        cfg = get_settings()
        dev_key = cfg.get("api_key") or None
        build_kwargs: dict[str, Any] = {"credentials": creds, "cache_discovery": False}
        if dev_key and mode == "none":
            build_kwargs = {"developerKey": dev_key, "cache_discovery": False}
        service = build(service_name, version, **build_kwargs)
        return service, mode, msg
    except Exception as exc:
        return None, mode, f"Erro ao inicializar cliente Google API ({service_name} {version}): {exc}"


def get_account_status(interactive: bool = False, settings_override: Optional[dict] = None) -> Tuple[bool, dict[str, Any]]:
    """Return structured status about the currently connected Google account."""
    cfg = get_settings(settings_override)
    cred_file = discover_credentials_file(cfg["credentials_path"])
    token_path = Path(cfg["token_path"]).expanduser()
    creds, mode, msg = load_credentials(interactive=interactive, settings_override=settings_override)

    info: dict[str, Any] = {
        "connected": creds is not None or bool(cfg.get("api_key")),
        "auth_mode": mode if creds is not None else ("api_key" if cfg.get("api_key") else "none"),
        "api_key_configured": bool(cfg.get("api_key")),
        "message": msg,
        "credentials_file": str(cred_file) if cred_file else "none",
        "token_file_exists": token_path.is_file(),
        "timezone": cfg["timezone"],
        "calendar_id": cfg["calendar_id"],
    }
    if creds is None:
        return False, info

    # Try fetching userinfo or Drive about info to verify live connectivity
    try:
        from googleapiclient.discovery import build
        if mode == "oauth_user":
            oauth2 = build("oauth2", "v2", credentials=creds, cache_discovery=False)
            me = oauth2.userinfo().get().execute()
            info["email"] = me.get("email", "")
            info["name"] = me.get("name", "")
        else:
            drive = build("drive", "v3", credentials=creds, cache_discovery=False)
            about = drive.about().get(fields="user(displayName,emailAddress)").execute()
            user = about.get("user") or {}
            info["email"] = user.get("emailAddress", getattr(creds, "service_account_email", ""))
            info["name"] = user.get("displayName", "Service Account")
    except Exception as exc:
        info["email"] = getattr(creds, "service_account_email", "")
        info["verify_note"] = str(exc)

    return True, info


def test_or_authenticate_ui(values: dict) -> Tuple[bool, str]:
    """Callback for the 'CONECTAR / VERIFICAR CONTA GOOGLE' button in PluginSettingsOverlay."""
    ok, info = get_account_status(interactive=True, settings_override=values)
    if ok:
        email = info.get("email") or "conta conectada"
        mode = info.get("auth_mode")
        return True, f"Conectado ({mode}): {email}"
    return False, info.get("message") or "Não conectado."


# Shared settings schema so `PluginSettingsOverlay` renders a single unified
# configuration form for the entire Google suite.
SHARED_PLUGIN_SETTINGS = {
    "namespace": NAMESPACE,
    "title": "GOOGLE ECOSYSTEM (GMAIL · CALENDAR · DRIVE · DOCS · SHEETS · TASKS · CONTACTS · YOUTUBE)",
    "fields": [
        {
            "key": "api_key",
            "label": "Google Cloud API Key (AIzaSy...)",
            "type": "password",
            "default": "",
            "placeholder": "AIzaSy...",
        },
        {
            "key": "credentials_path",
            "label": "Caminho do credentials.json (OAuth Desktop ou Service Account)",
            "type": "text",
            "default": str(DEFAULT_CREDENTIALS_PATH),
            "placeholder": "config/integrations/google_credentials.json",
        },
        {
            "key": "client_id",
            "label": "OAuth Client ID (opcional se não usar arquivo credentials.json)",
            "type": "text",
            "default": "",
            "placeholder": "1234567890-abcdef.apps.googleusercontent.com",
        },
        {
            "key": "client_secret",
            "label": "OAuth Client Secret (opcional se não usar arquivo credentials.json)",
            "type": "password",
            "default": "",
            "placeholder": "GOCSPX-...",
        },
        {
            "key": "calendar_id",
            "label": "ID da Agenda Padrão (Google Calendar)",
            "type": "text",
            "default": "primary",
            "placeholder": "primary ou seu_email@gmail.com",
        },
        {
            "key": "timezone",
            "label": "Fuso Horário",
            "type": "choice",
            "options": [
                "America/Sao_Paulo",
                "America/Manaus",
                "America/Fortaleza",
                "America/Cuiaba",
                "UTC",
            ],
            "default": "America/Sao_Paulo",
        },
        {
            "key": "auto_open_browser",
            "label": "Abrir navegador automaticamente no login OAuth",
            "type": "toggle",
            "default": True,
        },
    ],
    "action": {
        "label": "▸  CONECTAR / VERIFICAR CONTA GOOGLE",
        "run": test_or_authenticate_ui,
    },
}


# ── Date & Time parsing helpers for Calendar / Tasks ─────────────────────────
def parse_datetime_input(text: str, tz_name: Optional[str] = None, default_hour: int = 9) -> Optional[_dt.datetime]:
    """
    Parse natural or ISO date/time strings into a timezone-aware datetime.
    Supports:
      - ISO 8601: '2026-11-07T14:30:00', '2026-11-07 14:30', '2026-11-07'
      - Brazilian format: '07/11/2026 14:30', '07/11/2026', '07/11 às 14:30'
      - Relative keywords (PT/EN): 'hoje', 'amanhã'/'amanha', 'depois de amanhã',
        'today', 'tomorrow', 'now'/'agora', optionally followed by '14:30' or '14h30'.
    """
    tz = get_tz(tz_name)
    now = _dt.datetime.now(tz)
    raw = (text or "").strip()
    if not raw:
        return None

    low = raw.lower().strip()
    if low in ("agora", "now"):
        return now

    # Extract optional time component like 14:30, 14h30, 14h
    time_match = re.search(r"(?:às|as|at|\b)\s*(\d{1,2})(?::|h)(\d{2})?\b", low)
    hour, minute = default_hour, 0
    has_explicit_time = False
    if time_match:
        h_val = int(time_match.group(1))
        m_val = int(time_match.group(2) or 0)
        if 0 <= h_val <= 23 and 0 <= m_val <= 59:
            hour, minute = h_val, m_val
            has_explicit_time = True

    if low.startswith(("depois de amanhã", "depois de amanha")):
        base = now + _dt.timedelta(days=2)
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if low.startswith(("amanhã", "amanha", "tomorrow")):
        base = now + _dt.timedelta(days=1)
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if low.startswith(("hoje", "today")):
        base = now
        if not has_explicit_time:
            base = now + _dt.timedelta(hours=1)
            return base.replace(minute=0, second=0, microsecond=0)
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)

    # Try ISO 8601 directly
    iso_candidate = raw.replace("Z", "+00:00")
    try:
        dt = _dt.datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            # If only YYYY-MM-DD was provided without time
            if len(raw) == 10 and not has_explicit_time:
                dt = dt.replace(hour=default_hour, minute=0)
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    except ValueError:
        pass

    # Try DD/MM/YYYY or DD/MM
    br_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", raw)
    if br_match:
        day = int(br_match.group(1))
        month = int(br_match.group(2))
        year_s = br_match.group(3)
        year = int(year_s) if year_s else now.year
        if year < 100:
            year += 2000
        try:
            return _dt.datetime(year, month, day, hour, minute, tzinfo=tz)
        except ValueError:
            return None

    # If only a time like "15:00" or "15h30" was passed, assume today (or tomorrow if already passed)
    if has_explicit_time and len(raw) <= 10:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate < now - _dt.timedelta(minutes=5):
            candidate += _dt.timedelta(days=1)
        return candidate

    return None
