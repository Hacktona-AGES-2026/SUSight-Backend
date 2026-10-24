"""Load a scored queue (fila.json from `susight.scoring`) into a local database with demo accounts.

    uv run --no-sync python tools/import_dataset_queue.py --queue /caminho/pontuado/fila.json \
        --database data/dataset.sqlite3
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from susight.tribunal.guards import validate_queue
from susight.tribunal.models import QueuePatient
from susight.tribunal.store import Store

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--queue", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--treated", help="pasta do tratamento (solicitacoes.jsonl), para ler o procedimento")
    parser.add_argument("--procedures", help="procedimentos.csv do dataset, para o porte")
    parser.add_argument(
        "--events", help="eventos_clinicos.csv do dataset, para o historico do paciente da demo"
    )
    parser.add_argument("--password", default="demo1234")
    parser.add_argument("--patient-id", default="PAC-00152")
    parser.add_argument("--patient-cpf", default="52998224725")
    parser.add_argument("--patient-code", default="123456")
    args = parser.parse_args()
    path = Path(args.database)
    if path.exists():
        parser.exit(1, f"Erro: {path} ja existe; apague-o para importar de novo\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    porte, entry_date = {}, {}
    if args.treated and args.procedures:
        with open(args.procedures, encoding="utf-8") as stream:
            by_proc = {r["procedimento_id"]: r["porte"] for r in csv.DictReader(stream)}
        for line in (Path(args.treated) / "solicitacoes.jsonl").read_text().splitlines():
            item = json.loads(line)
            porte[item["solicitacao_id"]] = by_proc.get(item["normalizado"]["procedimento_id"])
            entry_date[item["solicitacao_id"]] = item["normalizado"].get("data_entrada_fila")
    raw = json.loads(Path(args.queue).read_text())
    for r in raw:
        if porte.get(r["solicitacao_id"]):
            r["porte"] = porte[r["solicitacao_id"]]
    rows = validate_queue([{k: v for k, v in r.items() if k in QueuePatient.model_fields} for r in raw])
    store = Store(path)
    store.import_queue(rows, 0, "import-dataset")
    store.provision_account("medico-demo", "medico", [r["paciente_id"] for r in rows], args.password)
    store.provision_account("admin-demo", "admin", [], args.password)
    # Conta do app: o paciente da demonstracao, que ja esta na fila importada.
    mine = next(r for r in rows if r["paciente_id"] == args.patient_id)
    store.provision_account(args.patient_cpf, "paciente", [mine["paciente_id"]], args.patient_code)
    # Only the demo patient gets a lived-in profile; every other account starts empty.
    entered = entry_date.get(mine["solicitacao_id"])
    history = [(entered, "entrada_na_fila", "Entrada na fila de cirurgia eletiva.")] if entered else []
    if args.events:
        with open(args.events, encoding="utf-8") as stream:
            history += [
                (e["data_evento"], e["tipo_evento"], e["descricao"])
                for e in csv.DictReader(stream)
                if e["paciente_id"] == mine["paciente_id"]
            ]
    with store.db() as db:
        if entered:  # the import already logged an entry dated today; use the real one
            db.execute("DELETE FROM events WHERE sid=? AND tipo='entrada_na_fila'", (mine["solicitacao_id"],))
        for when, kind, text in sorted(history):
            db.execute(
                "INSERT INTO events(sid,paciente_id,tipo,actor,texto,created_at) VALUES (?,?,?,?,?,?)",
                (
                    mine["solicitacao_id"],
                    mine["paciente_id"],
                    kind,
                    "dataset",
                    text,
                    f"{when}T12:00:00+00:00",
                ),
            )
    store.add_contact(
        mine["paciente_id"], {"nome": "Marta Medeiros", "parentesco": "Filha", "telefone": "(51) 98888-0152"}
    )
    print(f"{len(rows)} solicitacoes importadas em {path}")
    print(f"Contas: medico-demo e admin-demo, senha {args.password}")
    print(
        f"App: CPF {args.patient_cpf}, codigo {args.patient_code} ({mine['paciente_id']}, {mine['solicitacao_id']})"
    )
