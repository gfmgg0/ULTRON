"""
Google Account & Authenticated YouTube integration plugin for ULTRON (`google_youtube_account`).

Capabilities:
  - status: check Google Ecosystem connection status, active account, and auth mode
  - authenticate: trigger or refresh OAuth 2.0 login in the browser
  - import_credentials: import a client_secret*.json / credentials.json file into ULTRON
  - my_playlists: list playlists in the user's YouTube account
  - liked_videos: list videos liked by the user on YouTube
  - subscriptions: list channels the user is subscribed to on YouTube
  - create_playlist: create a new playlist on the user's YouTube channel
  - add_to_playlist: add a video to a YouTube playlist
"""
from __future__ import annotations

import re
from typing import Any

from core import outcome
from plugins._google_core import (
    SHARED_PLUGIN_SETTINGS,
    get_account_status,
    get_service,
    import_credentials_file,
)

PLUGIN_SETTINGS = SHARED_PLUGIN_SETTINGS

PLUGIN = {
    "name": "google_youtube_account",
    "tier": "extra",
    "brief": "Check or connect Google Account OAuth, and manage personal YouTube playlists, likes, and subscriptions.",
    "description": (
        "Gerencia a conexão geral da Conta Google no ULTRON e os recursos autenticados da conta "
        "pessoal do YouTube de Gabriel: verificar estado da conexão Google (status), iniciar login "
        "OAuth 2.0 no navegador (authenticate), importar arquivo credentials.json (import_credentials), "
        "listar minhas playlists do YouTube (my_playlists), vídeos marcados com Gostei (liked_videos), "
        "canais inscritos (subscriptions), criar playlist (create_playlist) e adicionar vídeo a uma playlist "
        "(add_to_playlist). Para buscar ou resumir vídeos públicos do YouTube, use youtube_video."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "status",
                    "authenticate",
                    "import_credentials",
                    "my_playlists",
                    "liked_videos",
                    "subscriptions",
                    "create_playlist",
                    "add_to_playlist",
                ],
                "description": "Ação a executar na Conta Google ou no YouTube autenticado.",
            },
            "credentials_path": {
                "type": "STRING",
                "description": "Caminho do arquivo client_secret*.json / credentials.json em 'import_credentials'.",
            },
            "title": {
                "type": "STRING",
                "description": "Título da nova playlist em 'create_playlist'.",
            },
            "description": {
                "type": "STRING",
                "description": "Descrição da nova playlist em 'create_playlist'.",
            },
            "privacy_status": {
                "type": "STRING",
                "enum": ["private", "unlisted", "public"],
                "description": "Privacidade da playlist em 'create_playlist' (padrão 'private').",
            },
            "playlist_id": {
                "type": "STRING",
                "description": "ID da playlist para 'add_to_playlist'.",
            },
            "video_id": {
                "type": "STRING",
                "description": "ID ou URL do vídeo do YouTube para 'add_to_playlist'.",
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Máximo de itens retornados (padrão 15).",
            },
        },
        "required": ["action"],
    },
}


def _extract_video_id(raw: str) -> str:
    s = (raw or "").strip()
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", s)
    return m.group(1) if m else s


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()
    max_results = max(1, min(50, int(params.get("max_results") or 15)))

    try:
        if action == "status":
            ok, info = get_account_status(interactive=False)
            if ok:
                return outcome.done(
                    "google_account_status",
                    connected=True,
                    auth_mode=info.get("auth_mode", ""),
                    account=info.get("email") or info.get("name") or "conectado",
                    credentials_file=info.get("credentials_file", ""),
                    timezone=info.get("timezone", ""),
                    message=info.get("message", ""),
                )
            return outcome.failed("google_account_status", info.get("message") or "Conta Google não conectada.")

        if action == "authenticate":
            ok, info = get_account_status(interactive=True)
            if ok:
                return outcome.done(
                    "google_authenticate",
                    connected=True,
                    auth_mode=info.get("auth_mode", ""),
                    account=info.get("email") or info.get("name") or "conectado",
                    message=info.get("message", ""),
                )
            return outcome.failed("google_authenticate", info.get("message") or "Não foi possível autenticar a Conta Google.")

        if action == "import_credentials":
            ok, msg = import_credentials_file(str(params.get("credentials_path") or ""))
            if ok:
                return outcome.done("google_import_credentials", details=msg)
            return outcome.failed("google_import_credentials", msg)

        # ── YOUTUBE AUTHENTICATED ACTIONS ────────────────────────────────────────
        yt, _mode, err = get_service("youtube", "v3", require_user_oauth=True)
        if yt is None:
            return outcome.failed("google_youtube_account", err)

        if action == "my_playlists":
            res = yt.playlists().list(part="snippet,contentDetails", mine=True, maxResults=max_results).execute()
            items = res.get("items") or []
            if not items:
                return outcome.done("youtube_playlists", count=0, summary="Nenhuma playlist encontrada na sua conta do YouTube.")
            lines = [
                f"- ID={pl.get('id', '')} | {(pl.get('snippet') or {}).get('title', '')} "
                f"({(pl.get('contentDetails') or {}).get('itemCount', 0)} vídeos)"
                for pl in items
            ]
            return outcome.done("youtube_playlists", count=len(lines)) + "\n" + outcome.untrusted("youtube", "\n".join(lines))

        if action == "liked_videos":
            res = yt.videos().list(part="snippet", myRating="like", maxResults=max_results).execute()
            items = res.get("items") or []
            if not items:
                return outcome.done("youtube_liked", count=0, summary="Nenhum vídeo marcado com Gostei encontrado.")
            lines = [
                f"- ID={v.get('id', '')} | {(v.get('snippet') or {}).get('title', '')} | "
                f"Canal: {(v.get('snippet') or {}).get('channelTitle', '')} | https://youtu.be/{v.get('id', '')}"
                for v in items
            ]
            return outcome.done("youtube_liked", count=len(lines)) + "\n" + outcome.untrusted("youtube", "\n".join(lines))

        if action == "subscriptions":
            res = yt.subscriptions().list(part="snippet", mine=True, maxResults=max_results, order="alphabetical").execute()
            items = res.get("items") or []
            if not items:
                return outcome.done("youtube_subscriptions", count=0, summary="Nenhuma inscrição encontrada.")
            lines = [
                f"- {(s.get('snippet') or {}).get('title', '')}"
                for s in items
            ]
            return outcome.done("youtube_subscriptions", count=len(lines)) + "\n" + outcome.untrusted("youtube", "\n".join(lines))

        if action == "create_playlist":
            title = str(params.get("title") or "").strip()
            if not title:
                return outcome.failed("youtube_create_playlist", "Informe 'title' para criar a playlist.")
            priv = str(params.get("privacy_status") or "private").strip().lower()
            if priv not in ("private", "unlisted", "public"):
                priv = "private"
            created = (
                yt.playlists()
                .insert(
                    part="snippet,status",
                    body={
                        "snippet": {
                            "title": title,
                            "description": str(params.get("description") or "").strip(),
                        },
                        "status": {"privacyStatus": priv},
                    },
                )
                .execute()
            )
            pid = created.get("id", "")
            return outcome.done(
                "youtube_create_playlist",
                playlist_id=pid,
                title=title,
                privacy=priv,
                link=f"https://www.youtube.com/playlist?list={pid}",
            )

        if action == "add_to_playlist":
            pid = str(params.get("playlist_id") or "").strip()
            vid = _extract_video_id(str(params.get("video_id") or ""))
            if not pid or not vid:
                return outcome.failed("youtube_add_to_playlist", "Informe 'playlist_id' e 'video_id' (ou URL do vídeo).")
            yt.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": pid,
                        "resourceId": {"kind": "youtube#video", "videoId": vid},
                    }
                },
            ).execute()
            return outcome.done("youtube_add_to_playlist", playlist_id=pid, video_id=vid)

        return outcome.failed("google_youtube_account", f"Ação desconhecida: {action}")
    except Exception as exc:
        return outcome.failed("google_youtube_account", f"Erro na API Google/YouTube ({action}): {exc}")
