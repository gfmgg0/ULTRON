"""
Google Calendar & Google Meet integration plugin for ULTRON (`calendar_control`).

Capabilities:
  - today: list all events scheduled for today
  - upcoming: list upcoming events over the next N days
  - search: search events by keyword or date window
  - create: create a calendar event (with optional attendees and Google Meet link)
  - quick_add: create an event from a natural-language phrase
  - update: reschedule or modify an existing event
  - delete: cancel/remove an event
  - freebusy: check availability in a time range
  - calendars: list calendars in the Google account
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional
from uuid import uuid4

from core import outcome
from plugins._google_core import (
    SHARED_PLUGIN_SETTINGS,
    get_service,
    get_settings,
    get_tz,
    parse_datetime_input,
)

PLUGIN_SETTINGS = SHARED_PLUGIN_SETTINGS

PLUGIN = {
    "name": "calendar_control",
    "tier": "core",
    "brief": "Read, search, create (with Google Meet), update, and delete Google Calendar events.",
    "description": (
        "Integra o ULTRON ao Google Calendar e Google Meet de Gabriel: consultar agenda de hoje (today), "
        "próximos compromissos (upcoming), buscar eventos (search), agendar novo evento ou reunião com "
        "link do Google Meet (create, quick_add), reagendar/atualizar (update), cancelar/remover (delete), "
        "verificar disponibilidade (freebusy) e listar agendas (calendars)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "today",
                    "upcoming",
                    "search",
                    "create",
                    "quick_add",
                    "update",
                    "delete",
                    "freebusy",
                    "calendars",
                ],
                "description": "Ação a executar no Google Calendar.",
            },
            "summary": {
                "type": "STRING",
                "description": "Título/nome do evento (para create ou update) ou frase completa para quick_add.",
            },
            "start_time": {
                "type": "STRING",
                "description": "Data/hora de início (ISO '2026-11-08T14:00', '08/11/2026 14:00', 'hoje 16:00', 'amanhã 10:00').",
            },
            "end_time": {
                "type": "STRING",
                "description": "Data/hora de término opcional. Se omitido em 'create', usa 'duration_minutes' (padrão 60 min).",
            },
            "duration_minutes": {
                "type": "INTEGER",
                "description": "Duração do evento em minutos quando 'end_time' não é informado (padrão 60).",
            },
            "description": {
                "type": "STRING",
                "description": "Descrição ou pauta do evento.",
            },
            "location": {
                "type": "STRING",
                "description": "Local físico ou endereço do evento.",
            },
            "attendees": {
                "type": "STRING",
                "description": "E-mails dos participantes separados por vírgula.",
            },
            "with_meet": {
                "type": "BOOLEAN",
                "description": "Se verdadeiro em 'create', gera automaticamente um link de videoconferência do Google Meet.",
            },
            "event_id": {
                "type": "STRING",
                "description": "ID do evento (para update ou delete). Se omitido, busca pelo 'query' ou 'summary'.",
            },
            "query": {
                "type": "STRING",
                "description": "Termo de busca para localizar eventos (search, update, delete).",
            },
            "days": {
                "type": "INTEGER",
                "description": "Número de dias à frente para 'upcoming' (padrão 7).",
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Máximo de eventos a retornar (padrão 15).",
            },
            "calendar_id": {
                "type": "STRING",
                "description": "ID da agenda (padrão configurada ou 'primary').",
            },
        },
        "required": ["action"],
    },
}


def _format_event(ev: dict) -> str:
    eid = ev.get("id", "")
    title = ev.get("summary") or "(Sem título)"
    start_obj = ev.get("start") or {}
    end_obj = ev.get("end") or {}
    start_str = start_obj.get("dateTime") or start_obj.get("date") or ""
    end_str = end_obj.get("dateTime") or end_obj.get("date") or ""
    loc = ev.get("location") or ""
    meet = ev.get("hangoutLink") or ""
    parts = [f"- ID={eid} | {title} | Início: {start_str} | Fim: {end_str}"]
    if loc:
        parts.append(f"Local: {loc}")
    if meet:
        parts.append(f"Meet: {meet}")
    return " | ".join(parts)


def _find_event_id(service: Any, calendar_id: str, event_id: str, query: str, tz_name: str) -> Optional[dict]:
    eid = (event_id or "").strip()
    if eid:
        try:
            return service.events().get(calendarId=calendar_id, eventId=eid).execute()
        except Exception:
            pass
    q = (query or "").strip()
    if not q:
        return None
    tz = get_tz(tz_name)
    t_min = (_dt.datetime.now(tz) - _dt.timedelta(days=1)).isoformat()
    res = (
        service.events()
        .list(
            calendarId=calendar_id,
            q=q,
            timeMin=t_min,
            singleEvents=True,
            orderBy="startTime",
            maxResults=5,
        )
        .execute()
    )
    items = res.get("items") or []
    return items[0] if items else None


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "today").strip().lower()
    cfg = get_settings()
    calendar_id = str(params.get("calendar_id") or cfg["calendar_id"] or "primary").strip()
    tz_name = cfg["timezone"]
    tz = get_tz(tz_name)
    max_results = max(1, min(50, int(params.get("max_results") or 15)))

    service, auth_mode, err = get_service("calendar", "v3")
    if service is None:
        return outcome.failed("calendar_control", err)

    try:
        now = _dt.datetime.now(tz)

        if action == "today":
            start_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_day = start_day + _dt.timedelta(days=1)
            res = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=start_day.isoformat(),
                    timeMax=end_day.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=max_results,
                )
                .execute()
            )
            items = res.get("items") or []
            if not items:
                return outcome.done("calendar_today", count=0, date=start_day.strftime("%Y-%m-%d"), summary="Nenhum compromisso agendado para hoje.")
            formatted = "\n".join(_format_event(e) for e in items)
            return outcome.done("calendar_today", count=len(items), date=start_day.strftime("%Y-%m-%d")) + "\n" + outcome.untrusted("calendar", formatted)

        if action == "upcoming":
            days = max(1, min(90, int(params.get("days") or 7)))
            t_max = now + _dt.timedelta(days=days)
            res = (
                service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=now.isoformat(),
                    timeMax=t_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=max_results,
                )
                .execute()
            )
            items = res.get("items") or []
            if not items:
                return outcome.done("calendar_upcoming", count=0, days=days, summary=f"Nenhum evento nos próximos {days} dias.")
            formatted = "\n".join(_format_event(e) for e in items)
            return outcome.done("calendar_upcoming", count=len(items), days=days) + "\n" + outcome.untrusted("calendar", formatted)

        if action == "search":
            q = str(params.get("query") or params.get("summary") or "").strip()
            start_dt = parse_datetime_input(str(params.get("start_time") or ""), tz_name) or (now - _dt.timedelta(days=30))
            end_dt = parse_datetime_input(str(params.get("end_time") or ""), tz_name) or (now + _dt.timedelta(days=180))
            kwargs: dict[str, Any] = {
                "calendarId": calendar_id,
                "timeMin": start_dt.isoformat(),
                "timeMax": end_dt.isoformat(),
                "singleEvents": True,
                "orderBy": "startTime",
                "maxResults": max_results,
            }
            if q:
                kwargs["q"] = q
            res = service.events().list(**kwargs).execute()
            items = res.get("items") or []
            if not items:
                return outcome.done("calendar_search", count=0, query=q, summary="Nenhum evento encontrado.")
            formatted = "\n".join(_format_event(e) for e in items)
            return outcome.done("calendar_search", count=len(items), query=q) + "\n" + outcome.untrusted("calendar", formatted)

        if action == "quick_add":
            text = str(params.get("summary") or params.get("query") or "").strip()
            if not text:
                return outcome.failed("calendar_quick_add", "Informe 'summary' com a descrição rápida do evento.")
            created = service.events().quickAdd(calendarId=calendar_id, text=text).execute()
            return outcome.done(
                "calendar_quick_add",
                event_id=created.get("id", ""),
                summary=created.get("summary", text),
                start=(created.get("start") or {}).get("dateTime") or (created.get("start") or {}).get("date", ""),
                link=created.get("htmlLink", ""),
            )

        if action == "create":
            summary = str(params.get("summary") or params.get("query") or "").strip()
            start_raw = str(params.get("start_time") or "").strip()
            if not summary or not start_raw:
                return outcome.failed("calendar_create", "Informe 'summary' (título) e 'start_time' (data/hora de início) para criar o evento.")
            start_dt = parse_datetime_input(start_raw, tz_name)
            if start_dt is None:
                return outcome.failed("calendar_create", f"Não foi possível interpretar a data/hora '{start_raw}'. Use ISO 'YYYY-MM-DD HH:MM' ou 'DD/MM/YYYY HH:MM'.")
            duration = max(5, min(1440, int(params.get("duration_minutes") or 60)))
            end_raw = str(params.get("end_time") or "").strip()
            end_dt = parse_datetime_input(end_raw, tz_name) if end_raw else (start_dt + _dt.timedelta(minutes=duration))
            if end_dt is None or end_dt <= start_dt:
                end_dt = start_dt + _dt.timedelta(minutes=duration)

            body: dict[str, Any] = {
                "summary": summary,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": tz_name},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": tz_name},
            }
            if params.get("description"):
                body["description"] = str(params["description"]).strip()
            if params.get("location"):
                body["location"] = str(params["location"]).strip()
            if params.get("attendees"):
                emails = [e.strip() for e in str(params["attendees"]).split(",") if "@" in e]
                if emails and auth_mode != "service_account":
                    body["attendees"] = [{"email": e} for e in emails]

            with_meet = bool(params.get("with_meet", False))
            insert_kwargs: dict[str, Any] = {"calendarId": calendar_id, "body": body}
            if with_meet and auth_mode != "service_account":
                body["conferenceData"] = {
                    "createRequest": {
                        "requestId": uuid4().hex,
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                }
                insert_kwargs["conferenceDataVersion"] = 1

            created = service.events().insert(**insert_kwargs).execute()
            return outcome.done(
                "calendar_create",
                event_id=created.get("id", ""),
                summary=created.get("summary", summary),
                start=start_dt.strftime("%Y-%m-%d %H:%M"),
                end=end_dt.strftime("%Y-%m-%d %H:%M"),
                meet_link=created.get("hangoutLink") or None,
                link=created.get("htmlLink", ""),
            )

        if action == "update":
            target = _find_event_id(
                service,
                calendar_id,
                str(params.get("event_id") or ""),
                str(params.get("query") or ""),
                tz_name,
            )
            if not target:
                return outcome.failed("calendar_update", "Evento não encontrado para atualizar. Informe 'event_id' ou 'query'.")
            eid = target["id"]
            if params.get("summary"):
                target["summary"] = str(params["summary"]).strip()
            if params.get("description"):
                target["description"] = str(params["description"]).strip()
            if params.get("location"):
                target["location"] = str(params["location"]).strip()
            if params.get("start_time"):
                new_start = parse_datetime_input(str(params["start_time"]), tz_name)
                if new_start:
                    duration = int(params.get("duration_minutes") or 60)
                    new_end = (
                        parse_datetime_input(str(params["end_time"]), tz_name)
                        if params.get("end_time")
                        else (new_start + _dt.timedelta(minutes=duration))
                    )
                    target["start"] = {"dateTime": new_start.isoformat(), "timeZone": tz_name}
                    target["end"] = {"dateTime": (new_end or (new_start + _dt.timedelta(minutes=duration))).isoformat(), "timeZone": tz_name}

            updated = service.events().update(calendarId=calendar_id, eventId=eid, body=target).execute()
            return outcome.done(
                "calendar_update",
                event_id=eid,
                summary=updated.get("summary", ""),
                start=(updated.get("start") or {}).get("dateTime") or (updated.get("start") or {}).get("date", ""),
            )

        if action == "delete":
            target = _find_event_id(
                service,
                calendar_id,
                str(params.get("event_id") or ""),
                str(params.get("query") or params.get("summary") or ""),
                tz_name,
            )
            if not target:
                return outcome.failed("calendar_delete", "Evento não encontrado para cancelar/excluir. Informe 'event_id' ou 'query'.")
            eid = target["id"]
            title = target.get("summary", "")
            service.events().delete(calendarId=calendar_id, eventId=eid).execute()
            return outcome.done("calendar_delete", event_id=eid, deleted_summary=title)

        if action == "freebusy":
            start_dt = parse_datetime_input(str(params.get("start_time") or "hoje"), tz_name) or now
            duration = max(15, min(1440, int(params.get("duration_minutes") or 120)))
            end_dt = (
                parse_datetime_input(str(params.get("end_time") or ""), tz_name)
                if params.get("end_time")
                else (start_dt + _dt.timedelta(minutes=duration))
            ) or (start_dt + _dt.timedelta(minutes=duration))
            fb = (
                service.freebusy()
                .query(
                    body={
                        "timeMin": start_dt.isoformat(),
                        "timeMax": end_dt.isoformat(),
                        "timeZone": tz_name,
                        "items": [{"id": calendar_id}],
                    }
                )
                .execute()
            )
            busy = ((fb.get("calendars") or {}).get(calendar_id) or {}).get("busy") or []
            status_str = "livre" if not busy else f"ocupado ({len(busy)} bloco(s))"
            return outcome.done(
                "calendar_freebusy",
                availability=status_str,
                window_start=start_dt.strftime("%Y-%m-%d %H:%M"),
                window_end=end_dt.strftime("%Y-%m-%d %H:%M"),
                busy_blocks=str(busy) if busy else "none",
            )

        if action == "calendars":
            res = service.calendarList().list().execute()
            cals = [
                f"{c.get('summary', '')} (id={c.get('id', '')})"
                for c in (res.get("items") or [])
            ]
            return outcome.done("calendar_list", count=len(cals), calendars="; ".join(cals))

        return outcome.failed("calendar_control", f"Ação desconhecida: {action}")
    except Exception as exc:
        return outcome.failed("calendar_control", f"Erro na API do Google Calendar: {exc}", requested_action=action)
