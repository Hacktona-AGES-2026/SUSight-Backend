"""Reproducible technical acceptance against the synthetic challenge dataset; no LLM calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from susight.artifacts import protect
from susight.dataset import treat
from susight.policy import POLICY_VERSION
from susight.priority import priority_group
from susight.scoring.engine import CRITERIA, Preferences, prepare, score_queue

SWINGS = {
    "deterioracao": 100,
    "limitacao": 80,
    "dor": 70,
    "comorbidades": 60,
    "asa": 40,
    "distancia": 20,
}


def demonstration_preferences(rows):
    total = sum(SWINGS.values())
    maxima = {"limitacao": 3, "asa": 4, "dor": 10, "comorbidades": 7, "deterioracao": 20, "distancia": 800}
    source = "Hipotese tecnica de demonstracao sintetica; sem validacao clinica ou atribuicao bibliografica"
    pairs = []
    for a in sorted(rows, key=lambda r: r["solicitacao_id"]):
        for b in sorted(rows, key=lambda r: r["solicitacao_id"]):
            if priority_group(a) != priority_group(b):
                continue
            if all(a["criterios"][c] >= b["criterios"][c] for c in CRITERIA) and any(
                a["criterios"][c] > b["criterios"][c] for c in CRITERIA
            ):
                pairs.append(
                    {
                        "antes": a["solicitacao_id"],
                        "depois": b["solicitacao_id"],
                        "fonte": "Referencia sintetica por dominancia monotona dentro do grupo; nao elicitacao medica",
                    }
                )
                break
        if len(pairs) == 10:
            break
    if len(pairs) < 10:
        raise ValueError("Menos de dez pares sinteticos dominantes sem espera; revise as referencias")
    return Preferences.model_validate(
        {
            "politica": POLICY_VERSION,
            "versao": "swing-demo-sem-espera-1",
            "demonstrativa": True,
            "swings_demonstrativos": SWINGS,
            "escalas": {
                c: {"minimo": 1 if c == "asa" else 0, "maximo": maxima[c], "fonte": source} for c in CRITERIA
            },
            "pesos": {
                c: {
                    "minimo": 0.75 * SWINGS[c] / total,
                    "maximo": min(1, 1.25 * SWINGS[c] / total),
                    "fonte": source,
                }
                for c in CRITERIA
            },
            "comparacoes": pairs,
            "janela": 1,
        }
    )


def accept(dataset, root):
    dataset, root = Path(dataset).resolve(), Path(root).resolve()
    if root.exists():
        raise ValueError("Use um diretorio de saida novo")
    if dataset == root or dataset in root.parents or root in dataset.parents:
        raise ValueError("Saida nao pode sobrepor originais")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dataset.iterdir() if p.is_file()}
    root.mkdir(parents=True, mode=0o700)
    quality = treat(dataset, root / "tratado")
    requests = [json.loads(line) for line in (root / "tratado/solicitacoes.jsonl").read_text().splitlines()]
    rows = [prepare(r) for r in requests if r["estado"] == "ativa"]
    prefs = demonstration_preferences(rows)
    with tempfile.TemporaryDirectory() as temporary:
        config = Path(temporary) / "preferences.json"
        config.write_text(prefs.model_dump_json(indent=2))
        result = score_queue(root / "tratado", config, root / "pontuado")
    verification = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("verificar_fila_priorizada.py")),
            str(root / "pontuado/fila_priorizada.csv"),
            "--dataset",
            str(dataset),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    unchanged = before == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in dataset.iterdir() if p.is_file()
    }
    evidence_index = {
        e["evidencia_id"]: e
        for e in map(json.loads, (root / "tratado/evidencias.jsonl").read_text().splitlines())
    }
    reviewed_sources = {}
    for record in requests:
        if record["estado"] != "excluida":
            continue
        checked = []
        for ref in record["evidencias_exclusao"]:
            if ref in evidence_index:
                source = evidence_index[ref]
                if (
                    source["polaridade"] != "afirmada"
                    or source.get("temporal") in {"historico", "futuro"}
                    or source["conceito"] not in {"desistencia", "cirurgia_outro_servico"}
                ):
                    raise ValueError("Fonte textual nao comprova encerramento nesta solicitacao")
                checked.append(
                    {
                        "referencia": ref,
                        "origem": source["arquivo"],
                        "linha": source["linha"],
                        "trecho": source["trecho"],
                        "tipo": "afirmacao_textual",
                    }
                )
            else:
                event = next((e for e in record["eventos"] if ref in e["ids_origem"]), None)
                if (
                    not event
                    or event["temporal"] != "durante_espera"
                    or event["resultado"] not in {"desistiu", "informou_cirurgia_outro_servico"}
                ):
                    raise ValueError("Evento nao comprova encerramento na espera atual")
                checked.append(
                    {
                        "referencia": ref,
                        "origem": "eventos_clinicos.csv",
                        "data": event["data_evento"],
                        "trecho": event["descricao"],
                        "tipo": event["resultado"],
                    }
                )
        reviewed_sources[record["solicitacao_id"]] = checked
    exclusions = [
        {
            "solicitacao_id": r["solicitacao_id"],
            "estado": r["estado"],
            "motivo": r["motivo"],
            "evidencias_exclusao": r["evidencias_exclusao"],
            "fontes_conferidas": reviewed_sources[r["solicitacao_id"]],
            "conferencia_tecnica": "origem preservada; exclusao explicita; revisar antes de uso clinico",
        }
        for r in requests
        if r["estado"] == "excluida"
    ]
    if not all(r["evidencias_exclusao"] for r in exclusions):
        raise ValueError("Exclusao sem evidencia de origem")
    duplicates = [
        {
            "solicitacao_id": r["solicitacao_id"],
            "decisao": "manter ativa e revisar contexto",
            "motivo": "equivalencia positiva nao comprovada",
        }
        for r in requests
        if "duplicata_possivel_revisar" in r["avisos"]
    ]
    report = {
        "politica": POLICY_VERSION,
        "natureza": "aceitacao_tecnica_em_dados_sinteticos",
        "validacao_clinica": False,
        "chamadas_llm": 0,
        "originais_intactos": unchanged,
        "qualidade": quality,
        "pontuacao": result,
        "verificador_oficial": {"codigo": verification.returncode, "saida": verification.stdout},
        "exclusoes": exclusions,
        "candidatos_duplicados": duplicates,
        "pendencias_humanas": [
            "Revisao clinica das escalas e preferencias",
            "Aceite das exclusoes pelo responsavel",
        ],
    }
    (root / "pontuado/aceitacao.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (root / "pontuado/preferencias-demonstrativas.json").write_text(prefs.model_dump_json(indent=2) + "\n")
    protect(root / "pontuado")
    if not unchanged or verification.returncode:
        raise ValueError("Falha de aceitacao; consulte aceitacao.json")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aceitacao tecnica completa, sem chamar IA")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()
    try:
        report = accept(args.dataset, args.output_root)
        print(
            json.dumps(
                {
                    "solicitacoes": report["pontuacao"]["solicitacoes"],
                    "verificador": report["verificador_oficial"]["codigo"],
                    "validacao_clinica": False,
                    "chamadas_llm": 0,
                },
                ensure_ascii=False,
            )
        )
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Erro: {exc}\n")
