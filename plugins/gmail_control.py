"""
Gmail integration plugin for ULTRON (`gmail_control`).

Capabilities:
  - unread: list unread Inbox emails
  - list: list recent emails
  - search: search emails using Gmail query syntax (from:, subject:, has:attachment, etc.)
  - read: read full message content, headers, and attachment filenames (wrapped as untrusted data)
  - send: send a new email (with optional CC, BCC, and file attachment)
  - reply: reply in-thread to an existing email
  - draft: create a draft email in Gmail
  - mark_read / mark_unread / star / archive / trash: manage message labels/state
  - labels: list Gmail labels
"""
from __future__ import annotations

import base64
import mimetypes
import re
from email.message import EmailMessage
from html import unescape
from pathlib import Path
from typing import Any, Optional

from core import outcome
from plugins._google_core import SHARED_PLUGIN_SETTINGS, get_service

PLUGIN_SETTINGS = SHARED_PLUGIN_SETTINGS

PLUGIN = {
    "name": "gmail_control",
    "tier": "core",
    "brief": "Read, search, send, reply, draft, and manage emails in Google Gmail.",
    "description": (
        "Integra o ULTRON ao Gmail da Conta Google de Gabriel: ler e-mails não lidos (unread), "
        "listar recentes (list), pesquisar por remetente/assunto/conteúdo (search), ler o corpo "
        "completo de um e-mail (read), enviar novo e-mail (send), responder na mesma conversa (reply), "
        "salvar rascunho (draft), marcar como lido/não lido, arquivar ou mover para lixeira "
        "(mark_read, mark_unread, star, archive, trash) e listar marcadores (labels)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "unread",
                    "list",
                    "search",
                    "read",
                    "send",
                    "reply",
                    "draft",
                    "mark_read",
                    "mark_unread",
                    "star",
                    "archive",
                    "trash",
                    "labels",
                ],
                "description": "Ação a executar no Gmail.",
            },
            "message_id": {
                "type": "STRING",
                "description": "ID da mensagem no Gmail (para read, reply, mark_read, archive, trash). Se omitido, usa 'query' para localizar a mensagem mais recente.",
            },
            "query": {
                "type": "STRING",
                "description": "Filtro de busca no Gmail (ex.: 'from:empresa', 'subject:nota fiscal', 'is:unread').",
            },
            "to": {
                "type": "STRING",
                "description": "Destinatário(s) do e-mail (separados por vírgula) para send ou draft.",
            },
            "cc": {
                "type": "STRING",
                "description": "Destinatários em cópia (CC), opcional.",
            },
            "bcc": {
                "type": "STRING",
                "description": "Destinatários em cópia oculta (BCC), opcional.",
            },
            "subject": {
                "type": "STRING",
                "description": "Assunto do e-mail para send ou draft.",
            },
            "body": {
                "type": "STRING",
                "description": "Corpo do texto do e-mail para send, reply ou draft.",
            },
            "attachment_path": {
                "type": "STRING",
                "description": "Caminho de arquivo local opcional para anexar ao e-mail.",
            },
            "reply_all": {
                "type": "BOOLEAN",
                "description": "Se verdadeiro em 'reply', responde a todos os participantes.",
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Quantidade máxima de e-mails retornados (1 a 25, padrão 8).",
            },
        },
        "required": ["action"],
    },
}


def _strip_html(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _headers_map(payload: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in payload.get("headers") or []:
        name = (h.get("name") or "").strip().lower()
        val = (h.get("value") or "").strip()
        if name:
            out[name] = val
    return out


def _extract_body_and_attachments(payload: dict) -> tuple[str, list[str]]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[str] = []

    def _walk(part: dict) -> None:
        mime = (part.get("mimeType") or "").lower()
        filename = (part.get("filename") or "").strip()
        body = part.get("body") or {}
        data = body.get("data")
        if filename:
            size = body.get("size", 0)
            attachments.append(f"{filename} ({size} bytes)")
        if data:
            try:
                decoded = base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", errors="replace")
                if mime == "text/plain":
                    plain_parts.append(decoded)
                elif mime == "text/html":
                    html_parts.append(_strip_html(decoded))
            except Exception:
                pass
        for sub in part.get("parts") or []:
            if isinstance(sub, dict):
                _walk(sub)

    _walk(payload or {})
    body_text = "\n\n".join(p.strip() for p in plain_parts if p.strip())
    if not body_text and html_parts:
        body_text = "\n\n".join(p.strip() for p in html_parts if p.strip())
    return body_text.strip(), attachments


def _resolve_message_id(service: Any, message_id: str, query: str) -> Optional[str]:
    mid = (message_id or "").strip()
    if mid:
        return mid
    q = (query or "").strip()
    if not q:
        return None
    res = service.users().messages().list(userId="me", q=q, maxResults=1).execute()
    msgs = res.get("messages") or []
    return msgs[0].get("id") if msgs else None


def _build_mime_message(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    attachment_path: str = "",
    in_reply_to: str = "",
    references: str = "",
) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to.strip()
    if cc.strip():
        msg["Cc"] = cc.strip()
    if bcc.strip():
        msg["Bcc"] = bcc.strip()
    msg["Subject"] = subject.strip()
    if in_reply_to.strip():
        msg["In-Reply-To"] = in_reply_to.strip()
    if references.strip():
        msg["References"] = references.strip()
    msg.set_content(body or "")

    if attachment_path and attachment_path.strip():
        att_file = Path(attachment_path.strip()).expanduser()
        if not att_file.is_file():
            raise FileNotFoundError(f"Arquivo de anexo não encontrado: {att_file}")
        ctype, encoding = mimetypes.guess_type(str(att_file))
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(
            att_file.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=att_file.name,
        )
    return msg


def _list_messages(service: Any, query: str, max_results: int) -> str:
    res = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = res.get("messages") or []
    if not messages:
        return outcome.done("gmail_list", count=0, query=query or "INBOX", summary="Nenhum e-mail encontrado para o filtro informado.")

    items: list[str] = []
    for m in messages[:max_results]:
        mid = m.get("id", "")
        detail = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=mid,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            )
            .execute()
        )
        hdrs = _headers_map(detail.get("payload") or {})
        sender = hdrs.get("from", "(desconhecido)")
        subj = hdrs.get("subject", "(sem assunto)")
        date = hdrs.get("date", "")
        snippet = (detail.get("snippet") or "").strip()
        unread_tag = "[NÃO LIDO] " if "UNREAD" in (detail.get("labelIds") or []) else ""
        items.append(f"- ID={mid} | {unread_tag}De: {sender} | Assunto: {subj} | Data: {date} | Prévia: {snippet[:140]}")

    joined = "\n".join(items)
    return outcome.done("gmail_list", count=len(items), query=query or "INBOX") + "\n" + outcome.untrusted("gmail_list", joined)


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "unread").strip().lower()
    max_results = max(1, min(25, int(params.get("max_results") or 8)))

    service, _mode, err = get_service("gmail", "v1", require_user_oauth=True)
    if service is None:
        return outcome.failed("gmail_control", err)

    try:
        if action == "unread":
            q = str(params.get("query") or "is:unread in:inbox").strip()
            return _list_messages(service, q, max_results)

        if action == "list":
            q = str(params.get("query") or "in:inbox").strip()
            return _list_messages(service, q, max_results)

        if action == "search":
            q = str(params.get("query") or "").strip()
            if not q:
                return outcome.failed("gmail_search", "Informe o parâmetro 'query' para pesquisar e-mails.")
            return _list_messages(service, q, max_results)

        if action == "read":
            mid = _resolve_message_id(service, params.get("message_id", ""), params.get("query", ""))
            if not mid:
                return outcome.failed("gmail_read", "Nenhum e-mail encontrado. Informe 'message_id' ou uma 'query' válida.")
            msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
            payload = msg.get("payload") or {}
            hdrs = _headers_map(payload)
            body_text, attachments = _extract_body_and_attachments(payload)
            if not body_text:
                body_text = (msg.get("snippet") or "(sem conteúdo textual)").strip()
            meta = (
                f"ID: {mid}\n"
                f"ThreadId: {msg.get('threadId', '')}\n"
                f"De: {hdrs.get('from', '')}\n"
                f"Para: {hdrs.get('to', '')}\n"
                f"Data: {hdrs.get('date', '')}\n"
                f"Assunto: {hdrs.get('subject', '(sem assunto)')}\n"
                f"Anexos: {', '.join(attachments) if attachments else 'nenhum'}\n\n"
                f"{body_text[:4500]}"
            )
            return outcome.done("gmail_read", message_id=mid, subject=hdrs.get("subject", "")) + "\n" + outcome.untrusted("email", meta)

        if action == "send":
            to = str(params.get("to") or "").strip()
            subject = str(params.get("subject") or "").strip()
            body = str(params.get("body") or "").strip()
            if not to or not subject:
                return outcome.failed("gmail_send", "Informe 'to' (destinatário) e 'subject' (assunto) para enviar o e-mail.")
            mime_msg = _build_mime_message(
                to=to,
                subject=subject,
                body=body,
                cc=str(params.get("cc") or ""),
                bcc=str(params.get("bcc") or ""),
                attachment_path=str(params.get("attachment_path") or ""),
            )
            raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return outcome.done("gmail_send", message_id=sent.get("id", ""), to=to, subject=subject)

        if action == "reply":
            mid = _resolve_message_id(service, params.get("message_id", ""), params.get("query", ""))
            body = str(params.get("body") or "").strip()
            if not mid or not body:
                return outcome.failed("gmail_reply", "Informe 'message_id' (ou 'query') e 'body' para responder ao e-mail.")
            orig = service.users().messages().get(userId="me", id=mid, format="metadata", metadataHeaders=["From", "To", "Cc", "Subject", "Message-ID", "References"]).execute()
            hdrs = _headers_map(orig.get("payload") or {})
            reply_to = hdrs.get("from", "")
            subj = hdrs.get("subject", "")
            if not subj.lower().startswith("re:"):
                subj = f"Re: {subj}"
            cc = hdrs.get("cc", "") if bool(params.get("reply_all", False)) else str(params.get("cc") or "")
            msg_id_hdr = hdrs.get("message-id", "")
            refs = (hdrs.get("references", "") + " " + msg_id_hdr).strip()
            mime_msg = _build_mime_message(
                to=reply_to,
                subject=subj,
                body=body,
                cc=cc,
                attachment_path=str(params.get("attachment_path") or ""),
                in_reply_to=msg_id_hdr,
                references=refs,
            )
            raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")
            sent = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw, "threadId": orig.get("threadId")})
                .execute()
            )
            return outcome.done("gmail_reply", message_id=sent.get("id", ""), to=reply_to, subject=subj)

        if action == "draft":
            to = str(params.get("to") or "").strip()
            subject = str(params.get("subject") or "").strip()
            body = str(params.get("body") or "").strip()
            if not to and not subject and not body:
                return outcome.failed("gmail_draft", "Informe 'to', 'subject' ou 'body' para criar o rascunho.")
            mime_msg = _build_mime_message(
                to=to or "undisclosed-recipients:;",
                subject=subject or "(Sem assunto)",
                body=body,
                cc=str(params.get("cc") or ""),
                bcc=str(params.get("bcc") or ""),
                attachment_path=str(params.get("attachment_path") or ""),
            )
            raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("ascii")
            draft = service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
            return outcome.done("gmail_draft", draft_id=draft.get("id", ""), to=to, subject=subject)

        if action in ("mark_read", "mark_unread", "star", "archive", "trash"):
            mid = _resolve_message_id(service, params.get("message_id", ""), params.get("query", ""))
            if not mid:
                return outcome.failed(f"gmail_{action}", "Informe 'message_id' ou 'query' para localizar o e-mail.")
            if action == "trash":
                service.users().messages().trash(userId="me", id=mid).execute()
                return outcome.done("gmail_trash", message_id=mid)
            add_labels: list[str] = []
            remove_labels: list[str] = []
            if action == "mark_read":
                remove_labels = ["UNREAD"]
            elif action == "mark_unread":
                add_labels = ["UNREAD"]
            elif action == "star":
                add_labels = ["STARRED"]
            elif action == "archive":
                remove_labels = ["INBOX"]
            service.users().messages().modify(
                userId="me",
                id=mid,
                body={"addLabelIds": add_labels, "removeLabelIds": remove_labels},
            ).execute()
            return outcome.done(f"gmail_{action}", message_id=mid)

        if action == "labels":
            res = service.users().labels().list(userId="me").execute()
            labels = [lbl.get("name", "") for lbl in (res.get("labels") or []) if lbl.get("name")]
            return outcome.done("gmail_labels", count=len(labels), labels=", ".join(sorted(labels)))

        return outcome.failed("gmail_control", f"Ação desconhecida: {action}")
    except Exception as exc:
        return outcome.failed("gmail_control", f"Erro na API do Gmail: {exc}", requested_action=action)
