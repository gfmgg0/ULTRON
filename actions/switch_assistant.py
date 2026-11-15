"""
Action to switch active assistant persona between ULTRON and FRIDAY.
- ULTRON: Mature low-register masculine voice ('Charon'), wine-red matrix (#922747), tactical/direct, addresses user as 'Chefe'.
- FRIDAY: Erudite cultured lady in her 40s-50s ('Aoede'), royal purple matrix (#8a2be2), dignified/articulate, addresses user as 'Senhor'.
"""
from __future__ import annotations

from typing import Any
from core import outcome
from memory.config_manager import AVAILABLE_PERSONAS, set_persona


def switch_assistant(
    parameters: dict[str, Any],
    player: Any = None,
    speak: Any = None,
    session_memory: Any = None,
) -> str:
    """
    Switches active assistant persona dynamically:
    persists settings to config, updates UI accent/title, and reconnects session with the new voice.
    """
    params = parameters or {}
    raw_target = str(params.get("assistant") or "").lower().strip()

    if "friday" in raw_target or "sexta" in raw_target:
        target_key = "friday"
    else:
        target_key = "ultron"

    persona = set_persona(target_key)
    name = persona["name"]
    voice = persona["voice"]
    color = persona["color"]
    address = persona["address"]

    if player and hasattr(player, "apply_assistant_switch"):
        player.apply_assistant_switch(name=name, user_name="", ui_color=color, voice=voice)

    if target_key == "friday":
        summary = (
            f"Controle transferido com sucesso para FRIDAY (F.R.I.D.A.Y.). "
            f"Voz feminina erudita ({voice}) e matriz holográfica roxa ({color}) ativadas. "
            f"Às suas ordens, {address} Gabriel."
        )
    else:
        summary = (
            f"Controle transferido com sucesso para ULTRON. "
            f"Voz grave tática ({voice}) e matriz holográfica vinho ({color}) ativadas. "
            f"Pronto para as ordens, {address}."
        )

    if player and hasattr(player, "write_log"):
        player.write_log(f"SYS: Persona alterada para {name} [{voice} · {color}]")

    return outcome.done("switch_assistant", summary=summary)


TOOL = {
    "name": "switch_assistant",
    "description": (
        "Switches the active AI assistant identity between ULTRON (masculine, tactical, wine-red core, 'Chefe') "
        "and FRIDAY (erudite cultured lady in her 40s-50s, feminine voice, royal purple core, 'Senhor'). "
        "Call this tool WHENEVER the user asks to switch, change, or activate Friday or Ultron "
        "(e.g. 'mudar para Friday', 'chame a Friday', 'Friday assuma', 'trocar para Friday', "
        "'mude para Ultron', 'chame o Ultron', 'Ultron assuma', 'trocar para Ultron', 'volte para o Ultron')."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "assistant": {
                "type": "STRING",
                "description": "The assistant persona to activate: 'friday' or 'ultron'.",
            },
            "reason": {
                "type": "STRING",
                "description": "Optional user request context or reason for switching.",
            },
        },
        "required": ["assistant"],
    },
    "handler": switch_assistant,
}
