"""
Google Tasks & Google Contacts (People API) integration plugin for ULTRON (`google_tasks_contacts`).

Capabilities:
  - list_tasks / add_task / complete_task / delete_task / list_tasklists (Google Tasks API v1)
  - search_contacts / list_contacts / create_contact (Google People API v1)
"""
from __future__ import annotations

from typing import Any, Optional

from core import outcome
from plugins._google_core import (
    SHARED_PLUGIN_SETTINGS,
    get_service,
    get_settings,
    parse_datetime_input,
)

PLUGIN_SETTINGS = SHARED_PLUGIN_SETTINGS

PLUGIN = {
    "name": "google_tasks_contacts",
    "tier": "core",
    "brief": "Manage Google Tasks (to-dos) and search, list, or create Google Contacts.",
    "description": (
        "Integra o ULTRON ao Google Tasks (Tarefas) e Google Contacts (Contatos) de Gabriel: "
        "listar tarefas pendentes (list_tasks), criar tarefa (add_task), marcar tarefa como concluída "
        "(complete_task), excluir tarefa (delete_task), listar listas de tarefas (list_tasklists), "
        "buscar contatos por nome/e-mail/telefone (search_contacts), listar contatos (list_contacts) "
        "e criar novo contato no Google Contacts (create_contact)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "list_tasks",
                    "add_task",
                    "complete_task",
                    "delete_task",
                    "list_tasklists",
                    "search_contacts",
                    "list_contacts",
                    "create_contact",
                ],
                "description": "Ação a executar no Google Tasks ou Google Contacts.",
            },
            "title": {
                "type": "STRING",
                "description": "Título da tarefa (add_task, complete_task, delete_task) ou nome do contato.",
            },
            "notes": {
                "type": "STRING",
                "description": "Notas/observações da tarefa em add_task.",
            },
            "due_date": {
                "type": "STRING",
                "description": "Prazo da tarefa (ISO '2026-11-10', '10/11/2026', 'amanhã').",
            },
            "task_id": {
                "type": "STRING",
                "description": "ID da tarefa no Google Tasks (se omitido, busca pelo 'title' ou 'query').",
            },
            "tasklist_id": {
                "type": "STRING",
                "description": "ID da lista de tarefas (padrão '@default').",
            },
            "show_completed": {
                "type": "BOOLEAN",
                "description": "Se verdadeiro em 'list_tasks', inclui tarefas concluídas.",
            },
            "query": {
                "type": "STRING",
                "description": "Termo de busca para localizar tarefa ou contato (nome, e-mail ou telefone).",
            },
            "given_name": {
                "type": "STRING",
                "description": "Primeiro nome do contato para 'create_contact'.",
            },
            "family_name": {
                "type": "STRING",
                "description": "Sobrenome do contato para 'create_contact'.",
            },
            "email": {
                "type": "STRING",
                "description": "E-mail do contato para 'create_contact'.",
            },
            "phone": {
                "type": "STRING",
                "description": "Telefone do contato para 'create_contact'.",
            },
            "organization": {
                "type": "STRING",
                "description": "Empresa/organização do contato para 'create_contact'.",
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Máximo de itens retornados (padrão 20).",
            },
        },
        "required": ["action"],
    },
}


def _find_task(service: Any, tasklist_id: str, task_id: str, query: str) -> Optional[dict]:
    tid = (task_id or "").strip()
    if tid:
        try:
            return service.tasks().get(tasklist=tasklist_id, task=tid).execute()
        except Exception:
            pass
    q = (query or "").strip().lower()
    if not q:
        return None
    res = service.tasks().list(tasklist=tasklist_id, showCompleted=True, maxResults=50).execute()
    for t in res.get("items") or []:
        if q in (t.get("title") or "").lower():
            return t
    return None


def _format_person(p: dict) -> str:
    names = p.get("names") or []
    emails = p.get("emailAddresses") or []
    phones = p.get("phoneNumbers") or []
    orgs = p.get("organizations") or []
    display_name = names[0].get("displayName", "(Sem nome)") if names else "(Sem nome)"
    email_str = ", ".join(e.get("value", "") for e in emails if e.get("value")) or "sem e-mail"
    phone_str = ", ".join(ph.get("value", "") for ph in phones if ph.get("value")) or "sem telefone"
    org_str = f" | Org: {orgs[0].get('name', '')}" if orgs and orgs[0].get("name") else ""
    return f"- {display_name} | E-mail: {email_str} | Tel: {phone_str}{org_str}"


def run(parameters: dict, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "list_tasks").strip().lower()
    max_results = max(1, min(100, int(params.get("max_results") or 20)))

    try:
        # ── GOOGLE TASKS ─────────────────────────────────────────────────────────
        if action in ("list_tasks", "add_task", "complete_task", "delete_task", "list_tasklists"):
            tasks_svc, _mode, err = get_service("tasks", "v1", require_user_oauth=True)
            if tasks_svc is None:
                return outcome.failed("google_tasks_contacts", err)

            tasklist_id = str(params.get("tasklist_id") or "@default").strip() or "@default"

            if action == "list_tasklists":
                res = tasks_svc.tasklists().list(maxResults=25).execute()
                lists = [f"{tl.get('title', '')} (id={tl.get('id', '')})" for tl in (res.get("items") or [])]
                return outcome.done("tasks_lists", count=len(lists), tasklists="; ".join(lists))

            if action == "list_tasks":
                show_comp = bool(params.get("show_completed", False))
                res = (
                    tasks_svc.tasks()
                    .list(
                        tasklist=tasklist_id,
                        showCompleted=show_comp,
                        showHidden=show_comp,
                        maxResults=max_results,
                    )
                    .execute()
                )
                items = [t for t in (res.get("items") or []) if (t.get("title") or "").strip()]
                if not items:
                    return outcome.done("tasks_list", count=0, summary="Nenhuma tarefa pendente no Google Tasks.")
                lines = []
                for t in items:
                    st = "✓" if t.get("status") == "completed" else "○"
                    due = f" | Prazo: {t['due'][:10]}" if t.get("due") else ""
                    notes = f" | Nota: {t['notes']}" if t.get("notes") else ""
                    lines.append(f"- [{st}] ID={t.get('id', '')} | {t.get('title', '')}{due}{notes}")
                return outcome.done("tasks_list", count=len(lines)) + "\n" + outcome.untrusted("google_tasks", "\n".join(lines))

            if action == "add_task":
                title = str(params.get("title") or params.get("query") or "").strip()
                if not title:
                    return outcome.failed("tasks_add", "Informe 'title' com o nome da tarefa.")
                body: dict[str, Any] = {"title": title}
                if params.get("notes"):
                    body["notes"] = str(params["notes"]).strip()
                if params.get("due_date"):
                    dt = parse_datetime_input(str(params["due_date"]), get_settings().get("timezone"))
                    if dt:
                        body["due"] = dt.strftime("%Y-%m-%dT00:00:00.000Z")
                created = tasks_svc.tasks().insert(tasklist=tasklist_id, body=body).execute()
                return outcome.done(
                    "tasks_add",
                    task_id=created.get("id", ""),
                    title=created.get("title", title),
                    due=created.get("due"),
                )

            if action == "complete_task":
                target = _find_task(
                    tasks_svc,
                    tasklist_id,
                    str(params.get("task_id") or ""),
                    str(params.get("query") or params.get("title") or ""),
                )
                if not target:
                    return outcome.failed("tasks_complete", "Tarefa não encontrada no Google Tasks.")
                target["status"] = "completed"
                updated = tasks_svc.tasks().update(tasklist=tasklist_id, task=target["id"], body=target).execute()
                return outcome.done("tasks_complete", task_id=updated.get("id", ""), title=updated.get("title", ""))

            if action == "delete_task":
                target = _find_task(
                    tasks_svc,
                    tasklist_id,
                    str(params.get("task_id") or ""),
                    str(params.get("query") or params.get("title") or ""),
                )
                if not target:
                    return outcome.failed("tasks_delete", "Tarefa não encontrada no Google Tasks.")
                tasks_svc.tasks().delete(tasklist=tasklist_id, task=target["id"]).execute()
                return outcome.done("tasks_delete", task_id=target["id"], deleted_title=target.get("title", ""))

        # ── GOOGLE CONTACTS (PEOPLE API) ─────────────────────────────────────────
        if action in ("search_contacts", "list_contacts", "create_contact"):
            people, _mode, err = get_service("people", "v1", require_user_oauth=True)
            if people is None:
                return outcome.failed("google_tasks_contacts", err)

            if action == "search_contacts":
                q = str(params.get("query") or params.get("title") or "").strip()
                if not q:
                    return outcome.failed("contacts_search", "Informe 'query' com o nome, e-mail ou telefone do contato.")
                res = (
                    people.people()
                    .searchContacts(
                        query=q,
                        pageSize=min(25, max_results),
                        readMask="names,emailAddresses,phoneNumbers,organizations",
                    )
                    .execute()
                )
                results = [r.get("person") or {} for r in (res.get("results") or []) if r.get("person")]
                if not results:
                    return outcome.done("contacts_search", count=0, query=q, summary="Nenhum contato encontrado.")
                formatted = "\n".join(_format_person(p) for p in results)
                return outcome.done("contacts_search", count=len(results), query=q) + "\n" + outcome.untrusted("google_contacts", formatted)

            if action == "list_contacts":
                res = (
                    people.people()
                    .connections()
                    .list(
                        resourceName="people/me",
                        pageSize=max_results,
                        personFields="names,emailAddresses,phoneNumbers,organizations",
                        sortOrder="FIRST_NAME_ASCENDING",
                    )
                    .execute()
                )
                conns = res.get("connections") or []
                if not conns:
                    return outcome.done("contacts_list", count=0, summary="Nenhum contato salvo no Google Contacts.")
                formatted = "\n".join(_format_person(p) for p in conns)
                return outcome.done("contacts_list", count=len(conns)) + "\n" + outcome.untrusted("google_contacts", formatted)

            if action == "create_contact":
                given = str(params.get("given_name") or params.get("title") or "").strip()
                family = str(params.get("family_name") or "").strip()
                email = str(params.get("email") or "").strip()
                phone = str(params.get("phone") or "").strip()
                org = str(params.get("organization") or "").strip()
                if not given and not email and not phone:
                    return outcome.failed("contacts_create", "Informe 'given_name' (nome), 'email' ou 'phone' para criar o contato.")
                body: dict[str, Any] = {}
                if given or family:
                    body["names"] = [{"givenName": given, "familyName": family}]
                if email:
                    body["emailAddresses"] = [{"value": email}]
                if phone:
                    body["phoneNumbers"] = [{"value": phone}]
                if org:
                    body["organizations"] = [{"name": org}]
                created = people.people().createContact(body=body).execute()
                return outcome.done(
                    "contacts_create",
                    resource_name=created.get("resourceName", ""),
                    name=f"{given} {family}".strip(),
                    email=email or None,
                    phone=phone or None,
                )

        return outcome.failed("google_tasks_contacts", f"Ação desconhecida: {action}")
    except Exception as exc:
        return outcome.failed("google_tasks_contacts", f"Erro na API Google ({action}): {exc}")
