#!/bin/sh
# Volta o banco da demonstracao ao estado importado: Pedro (PAC-00152) na posicao 794, sem propostas.
#
#   tools/reset_demo.sh save    guarda o banco atual como base (rode logo depois de importar a fila)
#   tools/reset_demo.sh         restaura a base, reinicia a API na porta 8000 e mostra o estado
#
# A base e os dados expiram em 7 dias; passado isso, importe de novo com tools/import_dataset_queue.py.
set -eu
cd "$(dirname "$0")/.."
LIVE=data/dataset.sqlite3
BASE=data/dataset.baseline.sqlite3

if [ "${1:-}" = "save" ]; then
  cp "$LIVE" "$BASE"
  echo "Base guardada em $BASE"
  exit 0
fi

[ -f "$BASE" ] || { echo "Sem base: importe a fila e rode 'tools/reset_demo.sh save'." >&2; exit 1; }
lsof -ti tcp:8000 | xargs kill 2>/dev/null || true
sleep 1
rm -f "$LIVE" "$LIVE-wal" "$LIVE-shm"
cp "$BASE" "$LIVE"
PYTHONPATH=src nohup uv run --no-sync --env-file .env uvicorn susight.api:create_app --factory \
  --host 0.0.0.0 --port 8000 --workers 1 > /tmp/susight-api.log 2>&1 &
for _ in 1 2 3 4 5 6 7 8 9 10; do
  curl -s localhost:8000/health >/dev/null 2>&1 && break
  sleep 1
done
curl -s localhost:8000/health >/dev/null || { echo "A API nao subiu; veja /tmp/susight-api.log" >&2; exit 1; }
echo "Demo reiniciada: Pedro (CPF 529.982.247-25, codigo 123456) na posicao 794, sem propostas."
