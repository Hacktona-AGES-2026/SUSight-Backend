"""Load a scored queue (fila.json from `susight.scoring`) into a local database with demo accounts.

    uv run --no-sync python tools/import_dataset_queue.py --queue /caminho/pontuado/fila.json \
        --database data/dataset.sqlite3
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from susight.tribunal.guards import validate_queue
from susight.tribunal.models import QueuePatient
from susight.tribunal.store import Store

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--queue", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--password", default="demo1234")
    parser.add_argument("--patient-id", default="PAC-00152")
    parser.add_argument("--patient-cpf", default="52998224725")
    parser.add_argument("--patient-code", default="123456")
    args = parser.parse_args()
    path = Path(args.database)
    if path.exists():
        parser.exit(1, f"Erro: {path} ja existe; apague-o para importar de novo\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = validate_queue(
        [
            {k: v for k, v in r.items() if k in QueuePatient.model_fields}
            for r in json.loads(Path(args.queue).read_text())
        ]
    )
    store = Store(path)
    store.import_queue(rows, 0, "import-dataset")
    store.provision_account("medico-demo", "medico", [r["paciente_id"] for r in rows], args.password)
    store.provision_account("admin-demo", "admin", [], args.password)
    # Conta do app: o paciente da demonstracao, que ja esta na fila importada.
    mine = next(r for r in rows if r["paciente_id"] == args.patient_id)
    store.provision_account(args.patient_cpf, "paciente", [mine["paciente_id"]], args.patient_code)
    print(f"{len(rows)} solicitacoes importadas em {path}")
    print(f"Contas: medico-demo e admin-demo, senha {args.password}")
    print(
        f"App: CPF {args.patient_cpf}, codigo {args.patient_code} ({mine['paciente_id']}, {mine['solicitacao_id']})"
    )
