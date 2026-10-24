"""Descriptive synthetic-data review; no clinical weights are inferred."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

from susight.artifacts import protect, retention
from susight.dataset.core import normalize, read_inputs


def summarize(records, catalog):
    cells = Counter()
    missing = Counter()
    cid = Counter()
    for record in records:
        n = record["normalizado"]
        proc = catalog.get(n["procedimento_id"])
        if not proc:
            missing["procedimento_sem_vinculo"] += 1
        elif any(
            normalize(origin["raw"].get("especialidade", "")) != normalize(proc["especialidade"])
            for origin in record["originais"]
        ):
            missing["especialidade_divergente"] += 1
        porte = normalize(proc.get("porte", "")) if proc else ""
        if porte not in {"pequeno", "medio", "grande", "especial"}:
            missing["porte_ausente_ou_incompativel"] += 1
            porte = "nao_informado"
        asa = record["medidas_observadas"]["asa"]
        if asa is None:
            missing["asa_observado_ausente_ou_invalido"] += 1
        cells[n["especialidade"], porte, str(asa) if asa is not None else "ausente"] += 1
        if any(i["criterio"] == "asa" for i in record["imputacoes"]):
            missing["asa_imputado_na_pontuacao_nao_usado_na_tabela"] += 1
        cid[(n.get("cid") or "?")[0]] += 1
    denominators = Counter()
    for (specialty, porte, _), count in cells.items():
        denominators[specialty, porte] += count
    return {
        "solicitacoes": len(records),
        "unidade": "solicitacao_ativa_canonica; nao paciente independente",
        "qualidade": dict(sorted(missing.items())),
        "cid_por_letra_registrada_sem_hierarquia": dict(sorted(cid.items())),
        "asa_porte": [
            {
                "especialidade": specialty,
                "porte": porte,
                "asa_observado": asa,
                "quantidade": count,
                "denominador_porte_especialidade": denominators[specialty, porte],
                "proporcao": count / denominators[specialty, porte],
            }
            for (specialty, porte, asa), count in sorted(cells.items())
        ],
    }


def analyze(dataset, treated, output):
    source, folder, dest = (Path(p).resolve() for p in (dataset, treated, output))
    if dest.exists() or any(dest == p or dest in p.parents or p in dest.parents for p in (source, folder)):
        raise ValueError("Saida existente ou sobreposta as entradas")
    tables, hashes = read_inputs(source)
    manifest = json.loads((folder / "manifesto.json").read_text())
    now = time.time()
    if (
        manifest.get("gerado_por") != "susight-backend"
        or not manifest.get("criado_epoch", now + 1) <= now < manifest.get("expira_epoch", 0)
        or not 0 < manifest["expira_epoch"] - manifest["criado_epoch"] <= 7 * 24 * 3600
        or manifest.get("entrada_sha256") != hashes
    ):
        raise ValueError("Tratamento expirado, invalido ou de outro dataset")
    for name in ("solicitacoes.jsonl", "evidencias.jsonl"):
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != manifest["saida_sha256"].get(name):
            raise ValueError("Artefato tratado difere do manifesto: " + name)
    records = [json.loads(line) for line in (folder / "solicitacoes.jsonl").read_text().splitlines()]
    active = [r for r in records if r["estado"] == "ativa"]
    clean = [r for r in active if "duplicata_possivel_revisar" not in r["avisos"]]
    catalog = {r["raw"]["procedimento_id"]: r["raw"] for r in tables["procedimentos.csv"]}
    active_ids = {r["solicitacao_id"] for r in active}
    evidence = [json.loads(line) for line in (folder / "evidencias.jsonl").read_text().splitlines()]
    inventory = Counter(
        (e["campo"], e["conceito"], e["polaridade"], e.get("temporal", "sem_data"))
        for e in evidence
        if e["solicitacao_id"] in active_ids
    )
    report = {
        "natureza": "analise_descritiva_sintetica; nao validacao clinica ou pesos",
        "validacao_clinica": False,
        "cobertura_canonicas_por_estado": dict(sorted(Counter(r["estado"] for r in records).items())),
        "catalogo_procedimentos": len(catalog),
        "canonicas_sem_vinculo_incluindo_pendentes": sum(
            r["normalizado"]["procedimento_id"] not in catalog for r in records
        ),
        "principal": summarize(active, catalog),
        "sensibilidade_sem_grupos_suspeitos": summarize(clean, catalog),
        "suspeitas_retiradas_apenas_da_sensibilidade": len(active) - len(clean),
        "fila_alterada": False,
        "inventario_indicios_regras_existentes": [
            {
                "campo": field,
                "conceito": concept,
                "polaridade": polarity,
                "temporal": temporal,
                "quantidade": count,
            }
            for (field, concept, polarity, temporal), count in sorted(inventory.items())
        ],
        "limites": [
            "ASA imputado nao entra na tabela observada; ausencias permanecem identificadas.",
            "Indicios textuais nao sao diagnosticos nem estimativas individuais de mortalidade.",
            "Cobertura restrita aos conceitos das regras existentes; fatores fora delas nao foram extraidos.",
            "Contagens de indicios nao sao contagens de pacientes ou criterios adicionais de prioridade.",
            "Associacao ASA/porte nao determina causalidade, urgencia ou pesos; requer interpretacao clinica.",
            "Exclusao de suspeitas na sensibilidade nao confirma duplicidade e nao exclui da fila.",
        ],
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".analysis-", dir=dest.parent))
    try:
        report_path = staging / "analise.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        lines = [
            "# ASA × porte e cobertura de evidências",
            "",
            "Análise descritiva do dataset sintético. Sem validação clínica e sem definição de pesos.",
            "",
            f"Solicitações ativas canônicas: {len(active)}. Sensibilidade sem suspeitas: {len(clean)}.",
            "Unidade: solicitação, não paciente independente. Nenhuma mudança foi aplicada à fila.",
            "",
            "## Tabela principal (ASA observado)",
            "",
            "| Especialidade | Porte | ASA observado | Quantidade | Denominador | Proporção |",
            "|---|---|---|---:|---:|---:|",
        ]
        for cell in report["principal"]["asa_porte"]:
            specialty = cell["especialidade"].replace("|", "/").replace("\n", " ")
            lines.append(
                f"| {specialty} | {cell['porte']} | {cell['asa_observado']} | {cell['quantidade']} | {cell['denominador_porte_especialidade']} | {cell['proporcao']:.3f} |"
            )
        lines += ["", "## Limitações", ""] + ["- " + text for text in report["limites"]]
        lines += [
            "",
            "A tabela de sensibilidade, as ausências e o inventário agregado estão em `analise.json`.",
        ]
        (staging / "RELATORIO.md").write_text("\n".join(lines) + "\n")
        metadata = {
            **retention(),
            "expira_epoch": min(now + 7 * 24 * 3600, manifest["expira_epoch"]),
            "entrada_sha256": hashes,
            "tratamento_manifesto_sha256": hashlib.sha256(
                (folder / "manifesto.json").read_bytes()
            ).hexdigest(),
            "saida_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in staging.iterdir()},
        }
        (staging / "manifesto.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")
        protect(staging)
        staging.rename(dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analise descritiva ASA x porte; nao calcula pesos clinicos")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--treated", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = analyze(args.dataset, args.treated, args.output)
        print(json.dumps({"solicitacoes": result["principal"]["solicitacoes"], "validacao_clinica": False}))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"Erro: {exc}\n")
