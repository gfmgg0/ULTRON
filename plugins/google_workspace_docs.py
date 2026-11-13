"""
Google Docs, Google Sheets & Google Slides integration plugin for ULTRON (`google_workspace_docs`).

Capabilities:
  - create_doc / read_doc / append_doc / replace_in_doc (Google Docs API v1)
  - create_sheet / read_sheet / append_sheet / update_sheet (Google Sheets API v4)
  - create_presentation / read_presentation (Google Slides API v1)
"""
from __future__ import annotations

import json
from typing import Any, Optional

from core import outcome
from plugins._google_core import SHARED_PLUGIN_SETTINGS, get_service

PLUGIN_SETTINGS = SHARED_PLUGIN_SETTINGS

PLUGIN = {
    "name": "google_workspace_docs",
    "tier": "core",
    "brief": "Create, read, and edit Google Docs, Google Sheets spreadsheets, and Google Slides.",
    "description": (
        "Integra o ULTRON ao Google Docs, Google Sheets (Planilhas) e Google Slides (Apresentações) "
        "de Gabriel: criar documento (create_doc), ler documento (read_doc), adicionar texto a um "
        "documento (append_doc), substituir texto (replace_in_doc), criar planilha (create_sheet), "
        "ler células de planilha (read_sheet), adicionar linhas em planilha (append_sheet), "
        "atualizar células (update_sheet), criar apresentação (create_presentation) e ler slides (read_presentation)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "create_doc",
                    "read_doc",
                    "append_doc",
                    "replace_in_doc",
                    "create_sheet",
                    "read_sheet",
                    "append_sheet",
                    "update_sheet",
                    "create_presentation",
                    "read_presentation",
                ],
                "description": "Ação a executar no Google Docs, Sheets ou Slides.",
            },
            "file_id": {
                "type": "STRING",
                "description": "ID do documento, planilha ou apresentação. Se omitido, usa 'query' ou 'title' para localizar no Google Drive.",
            },
            "query": {
                "type": "STRING",
                "description": "Nome/título para buscar o documento, planilha ou apresentação no Google Drive.",
            },
            "title": {
                "type": "STRING",
                "description": "Título para criar novo Doc, Planilha ou Apresentação (ou buscar existente).",
            },
            "content": {
                "type": "STRING",
                "description": "Texto a inserir em create_doc, append_doc ou create_presentation.",
            },
            "find_text": {
                "type": "STRING",
                "description": "Texto a localizar em replace_in_doc.",
            },
            "replace_text": {
                "type": "STRING",
                "description": "Novo texto de substituição em replace_in_doc.",
            },
            "range_name": {
                "type": "STRING",
                "description": "Intervalo A1 no Google Sheets (ex.: 'Página1!A1:D20' ou 'A1:F50', padrão 'A1:Z50').",
            },
            "rows": {
                "type": "STRING",
                "description": (
                    "Dados para Google Sheets (create_sheet, append_sheet, update_sheet). "
                    "Pode ser JSON '[[\"Col1\",\"Col2\"],[\"Val1\",\"Val2\"]]' ou linhas separadas por quebra de linha / ';' e colunas por '|' ou ','."
                ),
            },
        },
        "required": ["action"],
    },
}


def _find_by_name_in_drive(name_query: str, mime_type: str) -> Optional[str]:
    q = (name_query or "").strip()
    if not q:
        return None
    drive, _mode, _err = get_service("drive", "v3")
    if drive is None:
        return None
    escaped = q.replace("'", "\\'")
    res = (
        drive.files()
        .list(
            q=f"trashed = false and mimeType = '{mime_type}' and name contains '{escaped}'",
            pageSize=3,
            orderBy="modifiedTime desc",
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = res.get("files") or []
    return files[0].get("id") if files else None


def _extract_doc_text(doc: dict) -> str:
    pieces: list[str] = []
    body = (doc.get("body") or {}).get("content") or []
    for elem in body:
        para = elem.get("paragraph")
        if para:
            for pe in para.get("elements") or []:
                tr = pe.get("textRun")
                if tr and tr.get("content"):
                    pieces.append(tr["content"])
        table = elem.get("table")
        if table:
            for row in table.get("tableRows") or []:
                row_cells: list[str] = []
                for cell in row.get("tableCells") or []:
                    cell_txt: list[str] = []
                    for ce in cell.get("content") or []:
                        p = ce.get("paragraph")
                        if p:
                            for pe in p.get("elements") or []:
                                tr = pe.get("textRun")
                                if tr and tr.get("content"):
                                    cell_txt.append(tr["content"].strip())
                    row_cells.append(" ".join(cell_txt))
                pieces.append(" | ".join(row_cells) + "\n")
    return "".join(pieces).strip()


def _parse_rows_input(raw: str) -> list[list[Any]]:
    text = (raw or "").strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                if all(isinstance(r, list) for r in parsed):
                    return parsed
                return [parsed]
        except Exception:
            pass
    lines = [ln.strip() for ln in (text.splitlines() if "\n" in text else text.split(";")) if ln.strip()]
    matrix: list[list[Any]] = []
    for ln in lines:
        sep = "|" if "|" in ln else ("," if "," in ln else "\t")
        matrix.append([c.strip() for c in ln.split(sep)])
    return matrix


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "").strip().lower()
    fid = str(params.get("file_id") or "").strip()
    query = str(params.get("query") or params.get("title") or "").strip()

    try:
        # ── GOOGLE DOCS ──────────────────────────────────────────────────────────
        if action in ("create_doc", "read_doc", "append_doc", "replace_in_doc"):
            docs, _mode, err = get_service("docs", "v1")
            if docs is None:
                return outcome.failed("google_workspace_docs", err)

            if action == "create_doc":
                title = str(params.get("title") or params.get("query") or "Novo Documento ULTRON").strip()
                created = docs.documents().create(body={"title": title}).execute()
                doc_id = created.get("documentId", "")
                content = str(params.get("content") or "").strip()
                if content and doc_id:
                    docs.documents().batchUpdate(
                        documentId=doc_id,
                        body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
                    ).execute()
                return outcome.done(
                    "docs_create",
                    document_id=doc_id,
                    title=title,
                    link=f"https://docs.google.com/document/d/{doc_id}/edit",
                )

            doc_id = fid or _find_by_name_in_drive(query, "application/vnd.google-apps.document") or ""
            if not doc_id:
                return outcome.failed(action, "Documento Google Docs não encontrado. Informe 'file_id' ou 'query'.")

            if action == "read_doc":
                doc = docs.documents().get(documentId=doc_id).execute()
                text = _extract_doc_text(doc)
                title = doc.get("title", "")
                return (
                    outcome.done("docs_read", document_id=doc_id, title=title)
                    + "\n"
                    + outcome.untrusted("google_doc", f"Título: {title}\n\n{text[:5000]}")
                )

            if action == "append_doc":
                content = str(params.get("content") or "").strip()
                if not content:
                    return outcome.failed("docs_append", "Informe 'content' com o texto a ser adicionado.")
                doc = docs.documents().get(documentId=doc_id).execute()
                body_content = (doc.get("body") or {}).get("content") or []
                end_index = max(1, int(body_content[-1].get("endIndex", 2)) - 1) if body_content else 1
                prefix = "\n" if end_index > 1 else ""
                docs.documents().batchUpdate(
                    documentId=doc_id,
                    body={"requests": [{"insertText": {"location": {"index": end_index}, "text": prefix + content}}]},
                ).execute()
                return outcome.done(
                    "docs_append",
                    document_id=doc_id,
                    title=doc.get("title", ""),
                    chars_added=len(content),
                    link=f"https://docs.google.com/document/d/{doc_id}/edit",
                )

            if action == "replace_in_doc":
                find_t = str(params.get("find_text") or "").strip()
                repl_t = str(params.get("replace_text") or "")
                if not find_t:
                    return outcome.failed("docs_replace", "Informe 'find_text' com o texto a ser substituído.")
                res = (
                    docs.documents()
                    .batchUpdate(
                        documentId=doc_id,
                        body={
                            "requests": [
                                {
                                    "replaceAllText": {
                                        "containsText": {"text": find_t, "matchCase": False},
                                        "replaceText": repl_t,
                                    }
                                }
                            ]
                        },
                    )
                    .execute()
                )
                replies = res.get("replies") or [{}]
                occ = ((replies[0].get("replaceAllText") or {}).get("occurrencesChanged")) or 0
                return outcome.done("docs_replace", document_id=doc_id, occurrences_changed=occ)

        # ── GOOGLE SHEETS ────────────────────────────────────────────────────────
        if action in ("create_sheet", "read_sheet", "append_sheet", "update_sheet"):
            sheets, _mode, err = get_service("sheets", "v4")
            if sheets is None:
                return outcome.failed("google_workspace_docs", err)

            if action == "create_sheet":
                title = str(params.get("title") or params.get("query") or "Nova Planilha ULTRON").strip()
                created = sheets.spreadsheets().create(body={"properties": {"title": title}}).execute()
                sid = created.get("spreadsheetId", "")
                rows = _parse_rows_input(str(params.get("rows") or ""))
                if rows and sid:
                    sheets.spreadsheets().values().update(
                        spreadsheetId=sid,
                        range="A1",
                        valueInputOption="USER_ENTERED",
                        body={"values": rows},
                    ).execute()
                return outcome.done(
                    "sheets_create",
                    spreadsheet_id=sid,
                    title=title,
                    rows_written=len(rows),
                    link=created.get("spreadsheetUrl") or f"https://docs.google.com/spreadsheets/d/{sid}/edit",
                )

            sid = fid or _find_by_name_in_drive(query, "application/vnd.google-apps.spreadsheet") or ""
            if not sid:
                return outcome.failed(action, "Planilha Google Sheets não encontrada. Informe 'file_id' ou 'query'.")

            rng = str(params.get("range_name") or ("A1:Z50" if action == "read_sheet" else "A1")).strip()

            if action == "read_sheet":
                meta = sheets.spreadsheets().get(spreadsheetId=sid, fields="properties(title),sheets(properties(title))").execute()
                doc_title = (meta.get("properties") or {}).get("title", "")
                # If range has no sheet prefix and default A1:Z50 fails, use first sheet
                try:
                    res = sheets.spreadsheets().values().get(spreadsheetId=sid, range=rng).execute()
                except Exception:
                    first_sheet = (((meta.get("sheets") or [{}])[0]).get("properties") or {}).get("title", "")
                    rng_qualified = f"'{first_sheet}'!{rng}" if first_sheet and "!" not in rng else rng
                    res = sheets.spreadsheets().values().get(spreadsheetId=sid, range=rng_qualified).execute()
                values = res.get("values") or []
                lines = [" | ".join(str(c) for c in row) for row in values[:60]]
                table_txt = "\n".join(lines) if lines else "(Planilha vazia neste intervalo)"
                return (
                    outcome.done("sheets_read", spreadsheet_id=sid, title=doc_title, rows=len(values))
                    + "\n"
                    + outcome.untrusted("google_sheet", f"Planilha: {doc_title} ({res.get('range', rng)})\n\n{table_txt[:5000]}")
                )

            if action in ("append_sheet", "update_sheet"):
                rows = _parse_rows_input(str(params.get("rows") or params.get("content") or ""))
                if not rows:
                    return outcome.failed(action, "Informe 'rows' com os valores a gravar na planilha.")
                if action == "append_sheet":
                    res = (
                        sheets.spreadsheets()
                        .values()
                        .append(
                            spreadsheetId=sid,
                            range=rng,
                            valueInputOption="USER_ENTERED",
                            insertDataOption="INSERT_ROWS",
                            body={"values": rows},
                        )
                        .execute()
                    )
                    upd = res.get("updates") or {}
                    return outcome.done(
                        "sheets_append",
                        spreadsheet_id=sid,
                        updated_range=upd.get("updatedRange", rng),
                        updated_rows=upd.get("updatedRows", len(rows)),
                        link=f"https://docs.google.com/spreadsheets/d/{sid}/edit",
                    )
                else:
                    res = (
                        sheets.spreadsheets()
                        .values()
                        .update(
                            spreadsheetId=sid,
                            range=rng,
                            valueInputOption="USER_ENTERED",
                            body={"values": rows},
                        )
                        .execute()
                    )
                    return outcome.done(
                        "sheets_update",
                        spreadsheet_id=sid,
                        updated_range=res.get("updatedRange", rng),
                        updated_cells=res.get("updatedCells", 0),
                        link=f"https://docs.google.com/spreadsheets/d/{sid}/edit",
                    )

        # ── GOOGLE SLIDES ────────────────────────────────────────────────────────
        if action in ("create_presentation", "read_presentation"):
            slides, _mode, err = get_service("slides", "v1")
            if slides is None:
                return outcome.failed("google_workspace_docs", err)

            if action == "create_presentation":
                title = str(params.get("title") or params.get("query") or "Nova Apresentação ULTRON").strip()
                created = slides.presentations().create(body={"title": title}).execute()
                pid = created.get("presentationId", "")
                return outcome.done(
                    "slides_create",
                    presentation_id=pid,
                    title=title,
                    link=f"https://docs.google.com/presentation/d/{pid}/edit",
                )

            pid = fid or _find_by_name_in_drive(query, "application/vnd.google-apps.presentation") or ""
            if not pid:
                return outcome.failed("slides_read", "Apresentação Google Slides não encontrada. Informe 'file_id' ou 'query'.")
            pres = slides.presentations().get(presentationId=pid).execute()
            slide_texts: list[str] = []
            for idx, sl in enumerate(pres.get("slides") or [], start=1):
                parts: list[str] = []
                for pe in sl.get("pageElements") or []:
                    shape = pe.get("shape") or {}
                    txt_elems = (shape.get("text") or {}).get("textElements") or []
                    for te in txt_elems:
                        tr = te.get("textRun")
                        if tr and tr.get("content"):
                            parts.append(tr["content"].strip())
                slide_texts.append(f"[Slide {idx}] " + " | ".join(p for p in parts if p))
            joined = "\n".join(slide_texts) or "(Sem texto nos slides)"
            return (
                outcome.done("slides_read", presentation_id=pid, title=pres.get("title", ""), slides=len(slide_texts))
                + "\n"
                + outcome.untrusted("google_slides", f"Apresentação: {pres.get('title', '')}\n\n{joined[:5000]}")
            )

        return outcome.failed("google_workspace_docs", f"Ação desconhecida: {action}")
    except Exception as exc:
        return outcome.failed("google_workspace_docs", f"Erro na API Google Workspace ({action}): {exc}")
