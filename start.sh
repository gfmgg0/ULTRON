#!/usr/bin/env bash
# Script de inicialização do seu assistente Mark-LVI personalizado
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# Ativa o ambiente virtual
source "$DIR/venv/bin/activate"

# Adiciona bibliotecas locais necessárias para o Qt6 (ex: libxcb-cursor)
if [ -d "$DIR/lib/usr/lib/x86_64-linux-gnu" ]; then
    export LD_LIBRARY_PATH="$DIR/lib/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
fi

# Inicia a aplicação
# Evita importar pacotes de outros ambientes (por exemplo, ROS).
exec env -u PYTHONPATH "$DIR/venv/bin/python" main.py "$@"
