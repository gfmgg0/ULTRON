"""
Ação para permitir que o ULTRON altere seu próprio código-fonte acionando o Antigravity (agy).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from core import outcome


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _find_agy_binary() -> Optional[Path]:
    """Localiza o binário do Antigravity CLI (agy)."""
    which_path = shutil.which("agy")
    if which_path:
        p = Path(which_path)
        if p.is_file() and os.access(p, os.X_OK):
            return p

    candidates = [
        Path.home() / ".gemini" / "bin" / "agy",
        Path("/usr/local/bin/agy"),
        Path("/usr/bin/agy"),
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return c

    return None


def modify_self_code(
    parameters: dict[str, Any],
    player: Any = None,
    speak: Any = None,
    session_memory: Any = None,
) -> str:
    """
    Executa alterações no código-fonte do ULTRON invocando o Antigravity como operador/engenheiro de software.
    """
    params = parameters or {}
    instruction = str(params.get("instruction") or "").strip()
    target_files = str(params.get("target_files") or "").strip()

    if not instruction:
        return "Por favor, especifique qual alteração de código você deseja que seja feita no ULTRON."

    base_dir = _get_base_dir()
    agy_bin = _find_agy_binary()

    if not agy_bin:
        err = (
            "Binário do Antigravity ('agy') não foi encontrado no sistema (~/.gemini/bin/agy). "
            "Certifique-se de que o Antigravity CLI está instalado e acessível."
        )
        if player and hasattr(player, "write_log"):
            player.write_log(f"ERR: {err}")
        return err

    if player and hasattr(player, "write_log"):
        player.write_log(f"SYS: [Antigravity] Solicitando alteração no código: {instruction[:100]}...")

    prompt = (
        f"Você é o Antigravity, atuando como engenheiro de software e desenvolvedor do projeto ULTRON.\n"
        f"O usuário Gabriel (Chefe), através da interface do ULTRON, solicitou a seguinte alteração diretamente no código-fonte:\n\n"
        f"INSTRUÇÃO DO CHEFE:\n{instruction}\n\n"
    )
    if target_files:
        prompt += f"ARQUIVOS ALVO OU MÓDULOS RELEVANTES:\n{target_files}\n\n"

    prompt += (
        f"DIRETRIZES OBRIGATÓRIAS:\n"
        f"1. Analise o repositório em {base_dir}.\n"
        f"2. Use suas ferramentas de edição de arquivos para aplicar as mudanças com precisão no código-fonte.\n"
        f"3. Se modificar arquivos Python (.py), verifique a sintaxe antes de concluir.\n"
        f"4. Forneça uma resposta final concisa em português explicando exatamente o que foi modificado e como funciona, "
        f"para que o ULTRON possa relatar a conclusão em voz alta para o Chefe.\n"
    )

    cmd = [
        str(agy_bin),
        "--model",
        "gemini-3.8-flash-high",
        "--dangerously-skip-permissions",
        "--add-dir",
        str(base_dir),
        "-p",
        prompt,
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(base_dir),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        msg = "O Antigravity demorou mais de 3 minutos para concluir a alteração de código. O processo foi interrompido."
        if player and hasattr(player, "write_log"):
            player.write_log(f"ERR: [Antigravity] Timeout ao modificar código.")
        return msg
    except Exception as exc:
        msg = f"Falha ao executar o Antigravity CLI: {exc}"
        if player and hasattr(player, "write_log"):
            player.write_log(f"ERR: {msg}")
        return msg

    if proc.returncode != 0:
        err_out = proc.stderr.strip() or proc.stdout.strip() or f"Código de saída {proc.returncode}"
        msg = f"O Antigravity retornou um erro ao tentar alterar o código: {err_out[:400]}"
        if player and hasattr(player, "write_log"):
            player.write_log(f"ERR: [Antigravity] {err_out[:200]}")
        return msg

    result_text = proc.stdout.strip()

    # Verifica arquivos alterados no git
    changed_files = ""
    try:
        git_res = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(base_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if git_res.returncode == 0 and git_res.stdout.strip():
            changed_files = git_res.stdout.strip()
    except Exception:
        pass

    if player and hasattr(player, "write_log"):
        player.write_log("SYS: [Antigravity] Código alterado com sucesso.")

    resp = f"Alteração no código concluída pelo Antigravity:\n\n{result_text}"
    if changed_files:
        resp += f"\n\nArquivos modificados no repositório:\n{changed_files}"

    return outcome.done("modify_self_code", summary=resp)


TOOL = {
    "name": "modify_self_code",
    "description": (
        "Modifies ULTRON's own source code, plugins, actions, UI, or configuration by dispatching an engineering task "
        "to Antigravity (agy). Call this WHENEVER the user asks you to modify, rewrite, improve, fix, or add features "
        "to your own code or files (e.g. 'altere seu código', 'mude seu código', 'adicione uma função no seu sistema', "
        "'peça ao Antigravity para modificar...', 'altere o arquivo X'). Antigravity will edit the files directly on disk."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "instruction": {
                "type": "STRING",
                "description": "Clear and detailed description of the modifications, features, or fixes to apply to ULTRON's code.",
            },
            "target_files": {
                "type": "STRING",
                "description": "Optional list or hints of relevant files (e.g., 'main.py, actions/new_tool.py, ui.py').",
            },
        },
        "required": ["instruction"],
    },
    "handler": modify_self_code,
}
