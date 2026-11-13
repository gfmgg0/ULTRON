"""
Google Drive & Google One storage integration plugin for ULTRON (`google_drive_control`).

Capabilities:
  - recent / list: list recent files or files inside a folder
  - search: search Drive by filename, content, or type (doc, sheet, slide, pdf, folder)
  - read: extract and read text from a Google Doc, Sheet, Slide, PDF, or text file on Drive
  - upload: upload a local file from the machine to Google Drive
  - download: download a Drive file (or export a Google Workspace file) to the local machine
  - create_folder: create a folder on Google Drive
  - share: get shareable link or grant access to an email address
  - trash: move a file to the Drive trash
  - storage_quota: inspect Google Drive / Google One storage usage
"""
from __future__ import annotations

import io
import mimetypes
from pathlib import Path
from typing import Any, Optional

from core import outcome
from plugins._google_core import SHARED_PLUGIN_SETTINGS, get_service

PLUGIN_SETTINGS = SHARED_PLUGIN_SETTINGS

_MIME_MAP = {
    "folder": "application/vnd.google-apps.folder",
    "doc": "application/vnd.google-apps.document",
    "sheet": "application/vnd.google-apps.spreadsheet",
    "slide": "application/vnd.google-apps.presentation",
    "pdf": "application/pdf",
}

PLUGIN = {
    "name": "google_drive_control",
    "tier": "core",
    "brief": "Search, list, read, upload, download, share, and check quota on Google Drive.",
    "description": (
        "Integra o ULTRON ao Google Drive de Gabriel: listar arquivos recentes (recent, list), "
        "pesquisar arquivos ou pastas por nome/tipo (search), ler conteúdo de documentos/planilhas/arquivos "
        "no Drive (read), enviar arquivo do computador para o Drive (upload), baixar arquivo do Drive "
        "para o computador (download), criar pasta (create_folder), compartilhar ou gerar link (share), "
        "mover para lixeira (trash) e consultar espaço usado no Google Drive/Google One (storage_quota)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "recent",
                    "list",
                    "search",
                    "read",
                    "upload",
                    "download",
                    "create_folder",
                    "share",
                    "trash",
                    "storage_quota",
                ],
                "description": "Ação a executar no Google Drive.",
            },
            "query": {
                "type": "STRING",
                "description": "Nome do arquivo ou termo de busca para search, read, download, share ou trash.",
            },
            "file_id": {
                "type": "STRING",
                "description": "ID do arquivo no Google Drive (se omitido, busca pelo 'query').",
            },
            "file_type": {
                "type": "STRING",
                "enum": ["any", "folder", "doc", "sheet", "slide", "pdf"],
                "description": "Filtro opcional de tipo de arquivo em 'search'.",
            },
            "folder_id": {
                "type": "STRING",
                "description": "ID da pasta no Google Drive (para list, upload ou create_folder).",
            },
            "name": {
                "type": "STRING",
                "description": "Nome da nova pasta (create_folder) ou nome de destino no upload.",
            },
            "local_path": {
                "type": "STRING",
                "description": "Caminho local no computador (arquivo de origem em 'upload' ou pasta/arquivo de destino em 'download').",
            },
            "convert_to_google_format": {
                "type": "BOOLEAN",
                "description": "Em 'upload', se verdadeiro converte .docx/.xlsx/.csv/.pptx para Google Docs/Sheets/Slides.",
            },
            "email": {
                "type": "STRING",
                "description": "E-mail para compartilhar o arquivo em 'share' (se omitido, apenas retorna o link do arquivo).",
            },
            "role": {
                "type": "STRING",
                "enum": ["reader", "commenter", "writer"],
                "description": "Permissão ao compartilhar em 'share' (padrão 'reader').",
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Quantidade máxima de arquivos listados (padrão 12).",
            },
        },
        "required": ["action"],
    },
}


def _resolve_file(service: Any, file_id: str, query: str) -> Optional[dict]:
    fid = (file_id or "").strip()
    fields = "id, name, mimeType, webViewLink, size, modifiedTime"
    if fid:
        try:
            return service.files().get(fileId=fid, fields=fields, supportsAllDrives=True).execute()
        except Exception:
            pass
    q = (query or "").strip()
    if not q:
        return None
    escaped = q.replace("'", "\\'")
    res = (
        service.files()
        .list(
            q=f"trashed = false and name contains '{escaped}'",
            pageSize=5,
            fields=f"files({fields})",
            orderBy="modifiedTime desc",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = res.get("files") or []
    return files[0] if files else None


def _format_file(f: dict) -> str:
    return (
        f"- ID={f.get('id', '')} | {f.get('name', '')} | "
        f"Tipo={f.get('mimeType', '')} | Modificado={f.get('modifiedTime', '')} | "
        f"Link={f.get('webViewLink', '')}"
    )


def _download_bytes(service: Any, file_meta: dict) -> tuple[bytes, str]:
    fid = file_meta["id"]
    mime = file_meta.get("mimeType", "")
    if mime == "application/vnd.google-apps.document":
        data = service.files().export(fileId=fid, mimeType="text/plain").execute()
        return (data if isinstance(data, bytes) else str(data).encode("utf-8")), ".txt"
    if mime == "application/vnd.google-apps.spreadsheet":
        data = service.files().export(fileId=fid, mimeType="text/csv").execute()
        return (data if isinstance(data, bytes) else str(data).encode("utf-8")), ".csv"
    if mime == "application/vnd.google-apps.presentation":
        data = service.files().export(fileId=fid, mimeType="text/plain").execute()
        return (data if isinstance(data, bytes) else str(data).encode("utf-8")), ".txt"
    data = service.files().get_media(fileId=fid, supportsAllDrives=True).execute()
    return (data if isinstance(data, bytes) else bytes(data)), ""


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "recent").strip().lower()
    max_results = max(1, min(50, int(params.get("max_results") or 12)))

    service, _mode, err = get_service("drive", "v3")
    if service is None:
        return outcome.failed("google_drive_control", err)

    try:
        if action in ("recent", "list"):
            folder_id = str(params.get("folder_id") or "").strip()
            q = "trashed = false"
            if folder_id:
                q += f" and '{folder_id}' in parents"
            res = (
                service.files()
                .list(
                    q=q,
                    pageSize=max_results,
                    orderBy="modifiedTime desc",
                    fields="files(id, name, mimeType, webViewLink, size, modifiedTime)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files = res.get("files") or []
            if not files:
                return outcome.done("drive_list", count=0, summary="Nenhum arquivo encontrado no Google Drive.")
            formatted = "\n".join(_format_file(f) for f in files)
            return outcome.done("drive_list", count=len(files)) + "\n" + outcome.untrusted("google_drive", formatted)

        if action == "search":
            q_raw = str(params.get("query") or params.get("name") or "").strip()
            ftype = str(params.get("file_type") or "any").strip().lower()
            clauses = ["trashed = false"]
            if q_raw:
                escaped = q_raw.replace("'", "\\'")
                clauses.append(f"(name contains '{escaped}' or fullText contains '{escaped}')")
            if ftype in _MIME_MAP:
                clauses.append(f"mimeType = '{_MIME_MAP[ftype]}'")
            res = (
                service.files()
                .list(
                    q=" and ".join(clauses),
                    pageSize=max_results,
                    orderBy="modifiedTime desc",
                    fields="files(id, name, mimeType, webViewLink, size, modifiedTime)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files = res.get("files") or []
            if not files:
                return outcome.done("drive_search", count=0, query=q_raw, summary="Nenhum arquivo correspondente no Google Drive.")
            formatted = "\n".join(_format_file(f) for f in files)
            return outcome.done("drive_search", count=len(files), query=q_raw) + "\n" + outcome.untrusted("google_drive", formatted)

        if action == "read":
            target = _resolve_file(service, str(params.get("file_id") or ""), str(params.get("query") or params.get("name") or ""))
            if not target:
                return outcome.failed("drive_read", "Arquivo não encontrado no Google Drive. Informe 'file_id' ou 'query'.")
            raw_bytes, _ext = _download_bytes(service, target)
            mime = target.get("mimeType", "")
            text = ""
            if mime == "application/pdf":
                try:
                    import PyPDF2
                    reader = PyPDF2.PdfReader(io.BytesIO(raw_bytes))
                    text = "\n".join((page.extract_text() or "") for page in reader.pages[:15])
                except Exception:
                    text = raw_bytes.decode("utf-8", errors="replace")
            else:
                text = raw_bytes.decode("utf-8", errors="replace")
            snippet = text.strip()[:5000] or "(Arquivo sem texto extraível)"
            header = f"Arquivo: {target.get('name', '')} (ID={target.get('id', '')}, Tipo={mime})\n\n{snippet}"
            return outcome.done("drive_read", file_id=target["id"], name=target.get("name", "")) + "\n" + outcome.untrusted("google_drive", header)

        if action == "upload":
            local_raw = str(params.get("local_path") or "").strip()
            if not local_raw:
                return outcome.failed("drive_upload", "Informe 'local_path' com o caminho do arquivo local a enviar.")
            local_file = Path(local_raw).expanduser()
            if not local_file.is_file():
                return outcome.failed("drive_upload", f"Arquivo local não encontrado: {local_file}")
            from googleapiclient.http import MediaFileUpload
            ctype, _ = mimetypes.guess_type(str(local_file))
            ctype = ctype or "application/octet-stream"
            meta: dict[str, Any] = {"name": str(params.get("name") or local_file.name).strip()}
            folder_id = str(params.get("folder_id") or "").strip()
            if folder_id:
                meta["parents"] = [folder_id]
            if bool(params.get("convert_to_google_format", False)):
                ext = local_file.suffix.lower()
                if ext in (".doc", ".docx", ".txt", ".md"):
                    meta["mimeType"] = _MIME_MAP["doc"]
                elif ext in (".xls", ".xlsx", ".csv"):
                    meta["mimeType"] = _MIME_MAP["sheet"]
                elif ext in (".ppt", ".pptx"):
                    meta["mimeType"] = _MIME_MAP["slide"]
            media = MediaFileUpload(str(local_file), mimetype=ctype, resumable=True)
            uploaded = (
                service.files()
                .create(body=meta, media_body=media, fields="id, name, webViewLink", supportsAllDrives=True)
                .execute()
            )
            return outcome.done(
                "drive_upload",
                file_id=uploaded.get("id", ""),
                name=uploaded.get("name", ""),
                link=uploaded.get("webViewLink", ""),
            )

        if action == "download":
            target = _resolve_file(service, str(params.get("file_id") or ""), str(params.get("query") or params.get("name") or ""))
            if not target:
                return outcome.failed("drive_download", "Arquivo não encontrado no Google Drive. Informe 'file_id' ou 'query'.")
            raw_bytes, export_ext = _download_bytes(service, target)
            dest_raw = str(params.get("local_path") or "").strip()
            fname = target.get("name") or f"drive_{target['id']}"
            if export_ext and not fname.lower().endswith(export_ext):
                fname += export_ext
            if dest_raw:
                dest = Path(dest_raw).expanduser()
                if dest.is_dir():
                    dest = dest / fname
            else:
                dl_dir = Path.home() / "Downloads"
                dl_dir.mkdir(parents=True, exist_ok=True)
                dest = dl_dir / fname
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw_bytes)
            return outcome.done("drive_download", file_id=target["id"], saved_to=str(dest), bytes=len(raw_bytes))

        if action == "create_folder":
            folder_name = str(params.get("name") or params.get("query") or "").strip()
            if not folder_name:
                return outcome.failed("drive_create_folder", "Informe 'name' com o nome da pasta a ser criada.")
            meta = {"name": folder_name, "mimeType": _MIME_MAP["folder"]}
            parent_id = str(params.get("folder_id") or "").strip()
            if parent_id:
                meta["parents"] = [parent_id]
            created = service.files().create(body=meta, fields="id, name, webViewLink", supportsAllDrives=True).execute()
            return outcome.done(
                "drive_create_folder",
                folder_id=created.get("id", ""),
                name=created.get("name", ""),
                link=created.get("webViewLink", ""),
            )

        if action == "share":
            target = _resolve_file(service, str(params.get("file_id") or ""), str(params.get("query") or params.get("name") or ""))
            if not target:
                return outcome.failed("drive_share", "Arquivo não encontrado no Google Drive.")
            email = str(params.get("email") or "").strip()
            role = str(params.get("role") or "reader").strip().lower()
            if role not in ("reader", "commenter", "writer"):
                role = "reader"
            if email:
                service.permissions().create(
                    fileId=target["id"],
                    body={"type": "user", "role": role, "emailAddress": email},
                    sendNotificationEmail=True,
                    supportsAllDrives=True,
                ).execute()
            return outcome.done(
                "drive_share",
                file_id=target["id"],
                name=target.get("name", ""),
                shared_with=email or "link_only",
                role=role if email else None,
                link=target.get("webViewLink", ""),
            )

        if action == "trash":
            target = _resolve_file(service, str(params.get("file_id") or ""), str(params.get("query") or params.get("name") or ""))
            if not target:
                return outcome.failed("drive_trash", "Arquivo não encontrado no Google Drive.")
            service.files().update(fileId=target["id"], body={"trashed": True}, supportsAllDrives=True).execute()
            return outcome.done("drive_trash", file_id=target["id"], trashed_name=target.get("name", ""))

        if action == "storage_quota":
            about = service.about().get(fields="user(displayName,emailAddress),storageQuota").execute()
            quota = about.get("storageQuota") or {}
            user = about.get("user") or {}
            used_gb = round(int(quota.get("usage", 0)) / (1024 ** 3), 2)
            drive_gb = round(int(quota.get("usageInDrive", 0)) / (1024 ** 3), 2)
            trash_gb = round(int(quota.get("usageInDriveTrash", 0)) / (1024 ** 3), 2)
            limit_raw = quota.get("limit")
            limit_gb = f"{round(int(limit_raw) / (1024 ** 3), 2)} GB" if limit_raw else "Ilimitado"
            return outcome.done(
                "drive_storage_quota",
                account=user.get("emailAddress", ""),
                used_gb=f"{used_gb} GB",
                drive_gb=f"{drive_gb} GB",
                trash_gb=f"{trash_gb} GB",
                limit=limit_gb,
            )

        return outcome.failed("google_drive_control", f"Ação desconhecida: {action}")
    except Exception as exc:
        return outcome.failed("google_drive_control", f"Erro na API do Google Drive: {exc}", requested_action=action)
