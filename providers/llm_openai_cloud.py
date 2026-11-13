"""Independent OpenAI settings so a cloud fallback does not replace Ollama."""
from dataclasses import replace
from .llm_openai import PROVIDER as COMPAT

PROVIDER = {
    **COMPAT,
    "id": "openai_cloud",
    "label": "OpenAI",
    "hint": "OpenAI API — independent of the local model settings",
    "catalog": tuple(entry for entry in COMPAT["catalog"] if entry["id"] == "openai"),
    "needs": tuple(replace(field, default="https://api.openai.com/v1")
                   if field.key == "base_url" else field
                   for field in COMPAT["needs"]),
}
