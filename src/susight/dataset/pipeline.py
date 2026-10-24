from __future__ import annotations

import csv
import hashlib
import json
import shutil
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from .core import (
    LIMITATIONS,
    REFERENCE,
    RULES,
    consolidate,
    extract,
    normalize,
    normalize_request,
    parse_date,
    read_inputs,
    stable_id,
)


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def jsonlines(path, rows):
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8"
    )


def treat(input_dir, output_dir, reference=REFERENCE):
    source, dest = Path(input_dir).resolve(), Path(output_dir).resolve()
    if source == dest or source in dest.parents or dest in source.parents:
        raise ValueError("Entrada e saida nao podem se sobrepor")
    if dest.exists():
        raise ValueError("Destino ja existe")
    tables, hashes = read_inputs(source)
    catalog = {r["raw"]["procedimento_id"]: r["raw"] for r in tables["procedimentos.csv"]}
    requests = [normalize_request(r, catalog, reference) for r in tables["fila_cirurgica.csv"]]
    originals = {r["solicitacao_id"]: r for r in requests}
    evidence = []
    for r in requests:
        for field in ["justificativa_clinica", "observacoes", "comorbidades"]:
            origin = r["originais"][0]["origens"][0]
            entries = extract(
                r["normalizado"].get(field, ""),
                {**origin, "campo": field, "solicitacao_id": r["solicitacao_id"]},
            )
            evidence.extend(entries)
            r["evidencias_ids"].extend(e["evidencia_id"] for e in entries)
    # Secondary CIDs are already coded facts, not diagnoses inferred from measurements.
    for r in requests:
        raw = r["normalizado"].get("cid_secundario", "")
        cid = "".join(c for c in raw.upper() if c not in ". ")
        concept = next(
            (
                concept
                for prefix, concept in [
                    ("I10", "has"),
                    ("E10", "dm"),
                    ("E11", "dm"),
                    ("E66", "obesidade"),
                    ("I50", "cardiopatia"),
                    ("J44", "dpoc"),
                ]
                if cid.startswith(prefix)
            ),
            None,
        )
        if concept:
            item = {
                **r["originais"][0]["origens"][0],
                "campo": "cid_secundario",
                "solicitacao_id": r["solicitacao_id"],
                "conceito": concept,
                "trecho": raw,
                "inicio": 0,
                "fim": len(raw),
                "polaridade": "afirmada",
                "natureza": "clinica_documentada",
                "regra": "cid_secundario:" + concept,
                "versao": RULES["version"],
            }
            item["evidencia_id"] = stable_id(item)
            evidence.append(item)
            r["evidencias_ids"].append(item["evidencia_id"])
    requests, aliases = consolidate(requests)
    by_id = {r["solicitacao_id"]: r for r in requests}
    events, dedup = [], {}
    for source_event in tables["eventos_clinicos.csv"]:
        raw = source_event["raw"]
        key = stable_id({k: v for k, v in raw.items() if k != "evento_id"})
        if key in dedup:
            dedup[key]["ids_origem"].append(raw["evento_id"])
            dedup[key]["origens"].extend(source_event["origens"])
            continue
        canonical = aliases.get(raw["solicitacao_id"])
        request = by_id.get(canonical)
        event_date = parse_date(raw["data_evento"])
        status = (
            "orfao"
            if not request
            else "paciente_divergente"
            if request["paciente_id"] != raw["paciente_id"]
            else "data_invalida"
            if not event_date
            else "vinculado"
        )
        if status == "vinculado":
            entry = parse_date(request["normalizado"]["data_entrada_fila"])
            temporal = (
                "futuro"
                if event_date > reference
                else "historico"
                if entry and event_date < entry
                else "durante_espera"
            )
        else:
            temporal = "indefinido"
        event = {
            **raw,
            "solicitacao_canonica_id": canonical,
            "ids_origem": [raw["evento_id"]],
            "origens": source_event["origens"],
            "situacao": status,
            "temporal": temporal,
        }
        events.append(event)
        dedup[key] = event
        if request and status != "vinculado":
            request["avisos"].append(f"evento:{raw['evento_id']}:{status}")
        if status == "vinculado":
            request["eventos"].append(event)
            origin = source_event["origens"][0]
            entries = extract(
                raw["descricao"],
                {
                    **origin,
                    "campo": "descricao",
                    "solicitacao_id": raw["solicitacao_id"],
                    "evento_id": raw["evento_id"],
                },
            )
            for e in entries:
                e["temporal"] = temporal
            evidence.extend(entries)
            request["evidencias_ids"].extend(e["evidencia_id"] for e in entries)
    ev_index = {e["evidencia_id"]: e for e in evidence}
    for r in requests:
        entries = [ev_index[i] for i in r["evidencias_ids"]]
        eligible = [e for e in entries if e.get("temporal") != "futuro"]
        terminal_events = [
            e
            for e in r["eventos"]
            if e["temporal"] != "futuro"
            and e["tipo_evento"] == "contato_telefonico"
            and e["resultado"] in {"desistiu", "informou_cirurgia_outro_servico"}
        ]
        terminal_text = [
            e
            for e in eligible
            if e["conceito"] in {"desistencia", "cirurgia_outro_servico"} and e["polaridade"] == "afirmada"
        ]
        contradiction = any(
            (e["conceito"] == "retomada" and e["polaridade"] == "afirmada")
            or (e["conceito"] in {"desistencia", "cirurgia_outro_servico"} and e["polaridade"] != "afirmada")
            for e in eligible
        )
        r["motivo"] = "ativa" if r["estado"] == "ativa" else ";".join(r["pendencias"])
        r["evidencias_exclusao"] = [e["evidencia_id"] for e in terminal_text] + [
            e["evento_id"] for e in terminal_events
        ]
        if terminal_text or terminal_events:
            if contradiction:
                r["avisos"].append("encerramento_contraditorio_revisar")
            else:
                r["estado"], r["motivo"] = "excluida", "desistencia_ou_cirurgia_outro_servico_confirmada"
        if any(
            e["conceito"] in {"desistencia", "cirurgia_outro_servico"} and e["polaridade"] != "afirmada"
            for e in eligible
        ):
            r["avisos"].append("encerramento_ambiguo_revisar")
        n = r["normalizado"]
        n["comorbidades_identificadas"] = sorted(
            {
                e["conceito"]
                for e in entries
                if e["conceito"] in {"has", "dm", "obesidade", "cardiopatia", "dpoc"}
                and e["polaridade"] == "afirmada"
                and e.get("temporal") != "futuro"
            }
        )
        n["alarme_textual"] = any(e["conceito"] == "alarme" for e in eligible)
        n["biopsia_positiva"] = any(
            e["tipo_evento"] == "biopsia" and e["resultado"] == "positivo" and e["temporal"] != "futuro"
            for e in r["eventos"]
        )
        if n["biopsia_positiva"] and n["oncologico_por_cid"] is not True:
            r["avisos"].append("biopsia_positiva_cid_divergente")
        if (
            n["oncologico_por_cid"] is not None
            and normalize(n.get("flag_oncologico", "")) in {"sim", "nao"}
            and (normalize(n["flag_oncologico"]) == "sim") != n["oncologico_por_cid"]
        ):
            r["avisos"].append("flag_oncologico_divergente")
        for concept, flag in [("dm", "flag_diabetico"), ("piora", "flag_piora_clinica")]:
            if (
                any(e["conceito"] == concept and e["polaridade"] == "afirmada" for e in eligible)
                and normalize(n.get(flag, "")) == "nao"
            ):
                r["avisos"].append(flag + "_divergente")
    pools = defaultdict(list)
    for r in requests:
        if r["estado"] == "ativa":
            for key, val in r["medidas_observadas"].items():
                if val is not None:
                    pools[r["normalizado"]["especialidade"], key].append((r["solicitacao_id"], val))
    for r in requests:
        if r["estado"] != "ativa":
            continue
        for key, val in r["medidas_observadas"].items():
            if val is not None:
                continue
            pool = pools[r["normalizado"]["especialidade"], key]
            if not pool:
                r["pendencias"].append(f"sem_mediana:{key}")
                r["estado"] = "pendente"
                continue
            values = (
                sorted(v for _, v in pool)
                if key != "limitacao_funcional"
                else sorted((v for _, v in pool), key=LIMITATIONS.index)
            )
            value = statistics.median(values) if key == "distancia_hospital_km" else values[len(values) // 2]
            r["medidas_pontuacao"][key] = value
            r["imputacoes"].append(
                {
                    "criterio": key,
                    "valor": value,
                    "especialidade": r["normalizado"]["especialidade"],
                    "populacao_ids": sorted(i for i, _ in pool),
                }
            )
            r["avisos"].append("dado_incompleto:" + key)
        if r["pendencias"]:
            r["motivo"] = ";".join(r["pendencias"])
    coverage = []
    for sid in sorted(originals):
        r = by_id[aliases[sid]]
        consolidated = aliases[sid] != sid
        coverage.append(
            {
                "solicitacao_id": sid,
                "solicitacao_canonica_id": aliases[sid],
                "estado": "consolidada" if consolidated else r["estado"],
                "motivo": "duplicata_compativel" if consolidated else r["motivo"],
                "evidencias_ids": json.dumps(r["evidencias_ids"], ensure_ascii=False),
            }
        )
    quality = {
        "entrada": {name: len(rows) for name, rows in tables.items()},
        "cobertura": dict(Counter(r["estado"] for r in coverage)),
        "eventos_unicos": len(events),
        "eventos_duplicados": sum(len(e["ids_origem"]) - 1 for e in events),
        "eventos_por_situacao": dict(Counter(e["situacao"] for e in events)),
        "imputacoes": sum(len(r["imputacoes"]) for r in requests),
        "avisos": dict(Counter(a for r in requests for a in r["avisos"])),
    }
    assert sum(quality["cobertura"].values()) == len(originals)
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".dataset-", dir=dest.parent))
    try:
        jsonlines(staging / "solicitacoes.jsonl", requests)
        jsonlines(staging / "eventos.jsonl", sorted(events, key=lambda e: e["evento_id"]))
        jsonlines(staging / "evidencias.jsonl", sorted(evidence, key=lambda e: e["evidencia_id"]))
        with (staging / "cobertura.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=list(coverage[0])
                if coverage
                else ["solicitacao_id", "solicitacao_canonica_id", "estado", "motivo", "evidencias_ids"],
            )
            writer.writeheader()
            writer.writerows(coverage)
        dump(staging / "qualidade.json", quality)
        decisions = [
            "# Decisões do tratamento",
            "",
            f"Referência: {reference.isoformat()}. Regras: {RULES['version']}.",
            "",
            "Mediana ordinal superior para ASA, EVA e limitação; mediana aritmética para distância.",
            "Duplicatas exigem contexto clínico conhecido e texto normalizado igual; conflitos ficam separados.",
            "Indícios textuais não são diagnóstico. Exclusão exige confirmação explícita e sem contradição.",
            "",
            "| Solicitação | Estado | Canônica | Motivo | Evidências |",
            "|---|---|---|---|---|",
        ]
        decisions.extend(
            f"| {c['solicitacao_id']} | {c['estado']} | {c['solicitacao_canonica_id']} | {c['motivo']} | {c['evidencias_ids']} |"
            for c in coverage
            if c["estado"] != "ativa"
        )
        (staging / "DECISOES.md").write_text("\n".join(decisions) + "\n", encoding="utf-8")
        output_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in staging.iterdir()}
        dump(
            staging / "manifesto.json",
            {
                "referencia": reference.isoformat(),
                "entrada_sha256": hashes,
                "regras_sha256": stable_id(RULES),
                "versao_regras": RULES["version"],
                "versao_formato": 1,
                "executado_em": datetime.now(UTC).isoformat(),
                "saida_sha256": output_hashes,
            },
        )
        staging.rename(dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return quality
