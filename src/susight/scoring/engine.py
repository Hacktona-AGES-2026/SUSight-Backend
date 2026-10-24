from __future__ import annotations

import csv
import hashlib
import heapq
import json
import math
import re
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.optimize import linprog

from susight.artifacts import protect, retention
from susight.dataset.core import LIMITATIONS, RULES
from susight.policy import POLICY_VERSION
from susight.priority import priority_group

CRITERIA = ["limitacao", "asa", "dor", "comorbidades", "deterioracao", "distancia"]
TOL = 1e-7
URGENT_CID = {"I200", "K403", "K400", "K420", "K430", "K800", "N132", "I832"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Scale(Strict):
    minimo: float
    maximo: float
    fonte: str = Field(min_length=3)

    @model_validator(mode="after")
    def valid_range(self):
        if self.maximo <= self.minimo:
            raise ValueError("Escala deve ter amplitude positiva")
        return self


class Weight(Strict):
    minimo: float = Field(ge=0, le=1)
    maximo: float = Field(ge=0, le=1)
    fonte: str = Field(min_length=3)

    @model_validator(mode="after")
    def valid_range(self):
        if self.minimo > self.maximo:
            raise ValueError("Faixa de peso invertida")
        return self


class Pair(Strict):
    antes: str
    depois: str
    fonte: str = Field(min_length=3)

    @model_validator(mode="after")
    def different(self):
        if self.antes == self.depois:
            raise ValueError("Comparacao de um paciente consigo mesmo")
        return self


class WeightOrder(Strict):
    maior: str
    menor: str
    fonte: str = Field(min_length=3)


class Preferences(Strict):
    politica: str
    versao: str = Field(min_length=1)
    demonstrativa: bool = False
    swings_demonstrativos: dict[str, float] | None = None
    escalas: dict[str, Scale]
    pesos: dict[str, Weight]
    ordem_pesos: list[WeightOrder] = Field(default_factory=list)
    comparacoes: list[Pair] = Field(min_length=10, max_length=20)
    janela: int = Field(default=1, ge=1, le=50)
    margem: float = Field(default=1e-5, ge=1e-6, le=0.01)

    @model_validator(mode="after")
    def all_criteria(self):
        if self.politica != POLICY_VERSION or "espera" in self.escalas or "espera" in self.pesos:
            raise ValueError("Politica antiga: gere preferencias sem espera para " + POLICY_VERSION)
        if self.swings_demonstrativos is not None and (
            set(self.swings_demonstrativos) != set(CRITERIA)
            or any(not math.isfinite(v) or v <= 0 for v in self.swings_demonstrativos.values())
        ):
            raise ValueError("Swings demonstrativos devem conter somente criterios ativos positivos")
        if set(self.escalas) != set(CRITERIA) or set(self.pesos) != set(CRITERIA):
            raise ValueError("Escalas e pesos devem conter somente os seis criterios ativos, sem espera")
        for order in self.ordem_pesos:
            if order.maior not in CRITERIA or order.menor not in CRITERIA or order.maior == order.menor:
                raise ValueError("Ordem de pesos invalida")
        if len({(p.antes, p.depois) for p in self.comparacoes}) != len(self.comparacoes):
            raise ValueError("Comparacoes repetidas")
        return self


def prepare(request):
    n, measures = request["normalizado"], request["medidas_pontuacao"]
    if request["estado"] != "ativa" or request.get("pendencias"):
        raise ValueError(f"{request['solicitacao_id']}: solicitacao pendente ou inativa")
    events = [e for e in request["eventos"] if e["situacao"] == "vinculado" and e["temporal"] != "futuro"]
    worsening = [
        e
        for e in events
        if e["tipo_evento"] in {"pronto_socorro", "internacao"}
        or (e["tipo_evento"], e["resultado"])
        in {("exame_imagem", "progressao"), ("consulta_reavaliacao", "piora")}
    ]
    during = [e for e in worsening if e["temporal"] == "durante_espera"]
    reports = [e for e in events if e["temporal"] == "durante_espera" and e["resultado"] == "relata_piora"]
    cid = n["cid"]
    if not cid or any(
        measures.get(k) is None
        for k in ["asa", "intensidade_dor_eva", "limitacao_funcional", "distancia_hospital_km"]
    ):
        raise ValueError(f"{request['solicitacao_id']}: criterio sem valor")
    # Adaptation of descriptions supplied in referencias/swalis.csv, not a diagnosis.
    if (n["oncologico_por_cid"] and during) or cid in URGENT_CID:
        swalis = ("A1", 15)
    elif n["oncologico_por_cid"] or n["biopsia_positiva"]:
        swalis = ("A2", 21)
    elif measures["intensidade_dor_eva"] >= 7 or measures["limitacao_funcional"] == "grave" or during:
        swalis = ("B", 60)
    elif measures["intensidade_dor_eva"] >= 4 or measures["limitacao_funcional"] == "moderada":
        swalis = ("C", 180)
    else:
        swalis = ("D", 360)
    severity = {"has": 1, "dm": 1, "obesidade": 1, "cardiopatia": 2, "dpoc": 2}
    criteria = {
        "limitacao": LIMITATIONS.index(measures["limitacao_funcional"]),
        "asa": measures["asa"],
        "dor": measures["intensidade_dor_eva"],
        "comorbidades": sum(severity[c] for c in n["comorbidades_identificadas"]),
        "deterioracao": sum(2 if e["tipo_evento"] == "internacao" else 1 for e in during)
        + 0.25 * len(reports),
        "distancia": measures["distancia_hospital_km"],
    }
    # Conservative: original missing measures never establish lack of urgency.
    observed = request["medidas_observadas"]
    no_urgency = (
        n["oncologico_por_cid"] is False
        and not n["biopsia_positiva"]
        and observed["intensidade_dor_eva"] is not None
        and observed["intensidade_dor_eva"] <= 3
        and observed["limitacao_funcional"] in {"nenhuma", "leve"}
        and cid not in URGENT_CID
        and not worsening
        and not n["alarme_textual"]
        and not reports
        and not any("revisar" in a for a in request["avisos"])
    )
    # This flag reproduces the challenge checker only; it is NOT a clinical finding.
    # Keep it separate from the conservative assessment above, especially for missing data.
    original = request["originais"][0]["raw"]
    original_events = [e for e in request["eventos"] if e["solicitacao_id"] == request["solicitacao_id"]]
    original_worsening = any(
        e["tipo_evento"] in {"pronto_socorro", "internacao"}
        or (e["tipo_evento"], e["resultado"])
        in {("biopsia", "positivo"), ("exame_imagem", "progressao"), ("consulta_reavaliacao", "piora")}
        for e in original_events
    )
    raw_pain = original.get("intensidade_dor_eva", "").strip()
    checker_quiet = (
        not n["oncologico_por_cid"]
        and (not raw_pain or raw_pain.isdigit() and int(raw_pain) <= 3)
        and original.get("limitacao_funcional", "").strip() in {"", "nenhuma", "leve"}
        and cid not in URGENT_CID
        and not original_worsening
        and not re.search(RULES["concepts"]["alarme"], original.get("justificativa_clinica", "").lower())
    )
    return {
        "politica": POLICY_VERSION,
        "solicitacao_id": request["solicitacao_id"],
        "paciente_id": request["paciente_id"],
        "criterios": criteria,
        "oncologico": n["oncologico_por_cid"],
        "sem_urgencia": bool(no_urgency),
        "sem_urgencia_verificador": bool(checker_quiet),
        "dias_em_fila": n["dias_em_fila"],
        "cid": cid,
        "swalis": swalis[0],
        "prioridade_regulacao": n.get("prioridade_regulacao"),
        "imputacoes": request["imputacoes"],
        "avisos": request["avisos"],
        "evidencias_ids": request["evidencias_ids"],
    }


class Incompatible(ValueError):
    def __init__(self, ids):
        self.restricoes = ids
        super().__init__("Restricoes incompatíveis: " + ", ".join(ids))


class ROR:
    def __init__(self, rows, preferences):
        self.rows = {r["solicitacao_id"]: r for r in rows}
        self.preferences = preferences
        self.nvars = 2 * len(CRITERIA)
        self.features = {sid: self.basis(r["criterios"]) for sid, r in self.rows.items()}
        self.constraints = []
        for i, criterion in enumerate(CRITERIA):
            v = np.zeros(self.nvars)
            v[2 * i : 2 * i + 2] = 1
            weight = preferences.pesos[criterion]
            self.constraints.extend(
                [(criterion + ":max", v, weight.maximo), (criterion + ":min", -v, -weight.minimo)]
            )
        for i, o in enumerate(preferences.ordem_pesos):
            v = np.zeros(self.nvars)
            high, low = CRITERIA.index(o.maior), CRITERIA.index(o.menor)
            v[2 * low : 2 * low + 2], v[2 * high : 2 * high + 2] = 1, -1
            self.constraints.append((f"ordem:{i}", v, -preferences.margem))
        for i, pair in enumerate(preferences.comparacoes):
            if pair.antes not in self.rows or pair.depois not in self.rows:
                raise ValueError(f"Comparacao {i}: solicitacao ausente/inativa")
            before, after = priority_group(self.rows[pair.antes]), priority_group(self.rows[pair.depois])
            if before > after:
                raise Incompatible([f"par:{i}:contraria_hierarquia"])
            if before < after:
                continue
            self.constraints.append(
                (
                    f"par:{i}:{pair.antes}>{pair.depois}",
                    self.features[pair.depois] - self.features[pair.antes],
                    -preferences.margem,
                )
            )
        self.solve(np.zeros(self.nvars))
        self.representative = self.center()
        self.cache = {}

    def basis(self, criteria):
        result = []
        for c in CRITERIA:
            scale = self.preferences.escalas[c]
            value = float(criteria[c])
            if not math.isfinite(value):
                raise ValueError("Criterio nao finito")
            x = min(1.0, max(0.0, (value - scale.minimo) / (scale.maximo - scale.minimo)))
            result.extend([min(2 * x, 1.0), max(0.0, 2 * x - 1)])
        return np.array(result)

    def raw_solve(self, objective, constraints):
        return linprog(
            objective,
            A_ub=[v for _, v, _ in constraints] or None,
            b_ub=[b for _, _, b in constraints] or None,
            A_eq=[np.ones(self.nvars)],
            b_eq=[1.0],
            bounds=[(0.0, 1.0)] * self.nvars,
            method="highs",
            options={"primal_feasibility_tolerance": 1e-9},
        )

    def solve(self, objective):
        result = self.raw_solve(objective, self.constraints)
        if result.status == 2:
            conflict = list(self.constraints)
            for item in list(conflict):
                trial = [x for x in conflict if x[0] != item[0]]
                check = self.raw_solve(np.zeros(self.nvars), trial)
                if check.status == 2:
                    conflict = trial
                elif not check.success:
                    raise RuntimeError("Falha numerica ao diagnosticar restricoes")
            raise Incompatible([i for i, _, _ in conflict])
        if not result.success:
            raise RuntimeError("Solver nao concluiu: " + result.message)
        return result

    def center(self):
        # Maximize minimum normalized slack; nonnegativity is included explicitly.
        rows = [(v, b) for _, v, b in self.constraints]
        rows += [(-np.eye(self.nvars)[i], 0.0) for i in range(self.nvars)]
        A = [np.r_[v, max(float(np.linalg.norm(v)), 1.0)] for v, _ in rows]
        result = linprog(
            np.r_[np.zeros(self.nvars), -1.0],
            A_ub=A,
            b_ub=[b for _, b in rows],
            A_eq=[np.r_[np.ones(self.nvars), 0.0]],
            b_eq=[1.0],
            bounds=[(0.0, 1.0)] * self.nvars + [(0.0, None)],
            method="highs",
        )
        if not result.success:
            raise RuntimeError("Nao foi possivel escolher funcao representativa")
        return result.x[: self.nvars]

    def relation(self, a, b):
        if (a, b) in self.cache:
            return self.cache[a, b]
        ga, gb = priority_group(self.rows[a]), priority_group(self.rows[b])
        if ga != gb:
            return {
                "a": a,
                "b": b,
                "min_diferenca": None,
                "max_diferenca": None,
                "a_necessario": ga < gb,
                "b_necessario": gb < ga,
                "a_possivel": ga < gb,
                "b_possivel": gb < ga,
                "incerto": False,
                "empate_necessario": False,
                "origem": "hierarquia_regra_de_ouro",
            }
        diff = self.features[a] - self.features[b]
        minimum = float(self.solve(diff).fun)
        maximum = -float(self.solve(-diff).fun)
        result = {
            "a": a,
            "b": b,
            "min_diferenca": minimum,
            "max_diferenca": maximum,
            "a_necessario": minimum >= -TOL,
            "b_necessario": maximum <= TOL,
            "a_possivel": maximum >= -TOL,
            "b_possivel": minimum <= TOL,
            "incerto": minimum < -TOL and maximum > TOL,
            "empate_necessario": abs(minimum) <= TOL and abs(maximum) <= TOL,
            "origem": "ror_mesmo_grupo",
        }
        self.cache[a, b] = result
        return result


def order_queue(rows, model):
    scores = {sid: float(v @ model.representative) for sid, v in model.features.items()}
    base = sorted(
        rows,
        key=lambda r: (
            priority_group(r),
            -scores[r["solicitacao_id"]],
            r["solicitacao_id"],
        ),
    )
    edges = {r["solicitacao_id"]: set() for r in rows}
    notes = {sid: [] for sid in edges}
    # Hard precedence. Check any reversal against ALL compatible value functions.
    for a in rows:
        for b in rows:
            sa, sb = a["solicitacao_id"], b["solicitacao_id"]
            if sa == sb:
                continue
            if priority_group(a) != priority_group(b):
                if priority_group(a) < priority_group(b):
                    edges[sa].add(sb)
                    notes[sa].append("hierarquia_regra_de_ouro")
                continue
            if abs(scores[sa] - scores[sb]) <= TOL and not np.array_equal(
                model.features[sa], model.features[sb]
            ):
                relation = model.relation(sa, sb)
                if relation["a_necessario"] and not relation["b_necessario"]:
                    edges[sa].add(sb)
            gold = a["oncologico"] and (b["sem_urgencia"] or b.get("sem_urgencia_verificador", False))
            if gold:
                if scores[sa] < scores[sb] - TOL and (
                    model.relation(sa, sb)["b_necessario"] and not model.relation(sa, sb)["a_necessario"]
                ):
                    raise ValueError(f"Trava contradiz ordem necessaria: {sa} antes de {sb}")
                edges[sa].add(sb)
                if gold:
                    notes[sa].append("regra_de_ouro")
    # Necessary relations for every reversed pair must remain respected after hard ordering.
    indegree = dict.fromkeys(edges, 0)
    for targets in edges.values():
        for sid in targets:
            indegree[sid] += 1
    rank = {r["solicitacao_id"]: i for i, r in enumerate(base)}
    ready = [(rank[sid], sid) for sid, d in indegree.items() if d == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        _, sid = heapq.heappop(ready)
        ordered.append(model.rows[sid])
        for target in sorted(edges[sid]):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, (rank[target], target))
    if len(ordered) != len(rows):
        raise ValueError("Ciclo entre travas de equidade e prioridades")
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            sa, sb = a["solicitacao_id"], b["solicitacao_id"]
            if rank[sa] > rank[sb] and (
                model.relation(sa, sb)["b_necessario"] and not model.relation(sa, sb)["a_necessario"]
            ):
                raise ValueError(f"Ordenacao viola relacao necessaria: {sb}>{sa}")
    return ordered, scores, {sid: sorted(set(v)) for sid, v in notes.items()}


def score_queue(input_dir, preferences_path, output_dir):
    folder, dest = Path(input_dir).resolve(), Path(output_dir).resolve()
    if dest.exists() or folder == dest or folder in dest.parents or dest in folder.parents:
        raise ValueError("Destino existente ou sobreposto a entrada")
    source_manifest = json.loads((folder / "manifesto.json").read_text())
    try:
        created, expires = float(source_manifest["criado_epoch"]), float(source_manifest["expira_epoch"])
        if (
            source_manifest["gerado_por"] != "susight-backend"
            or not 0 < expires - created <= 7 * 24 * 3600
            or not created <= time.time() < expires
        ):
            raise ValueError("Dados tratados expirados ou com manifesto invalido")
    except (KeyError, TypeError):
        raise ValueError("Gere novamente o tratamento com manifesto de validade") from None
    prefs = Preferences.model_validate_json(Path(preferences_path).read_text())
    raw = [json.loads(line) for line in (folder / "solicitacoes.jsonl").read_text().splitlines()]
    pending = [r["solicitacao_id"] for r in raw if r["estado"] == "pendente"]
    if pending:
        raise ValueError("Resolver pendencias antes de publicar fila: " + ", ".join(pending))
    rows = [prepare(r) for r in raw if r["estado"] == "ativa"]
    if not rows:
        raise ValueError("Fila ativa vazia")
    model = ROR(rows, prefs)
    ordered, scores, notes = order_queue(rows, model)
    relations = []
    for i, row in enumerate(ordered):
        for other in ordered[i + 1 : i + 1 + prefs.janela]:
            relations.append(model.relation(row["solicitacao_id"], other["solicitacao_id"]))
    # Reference comparisons cannot be displaced by hard rules.
    positions = {r["solicitacao_id"]: i + 1 for i, r in enumerate(ordered)}
    if any(positions[p.antes] >= positions[p.depois] for p in prefs.comparacoes):
        raise ValueError("Trava contradiz comparacao de referencia")
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".scoring-", dir=dest.parent))
    try:
        with (staging / "fila_priorizada.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["solicitacao_id", "posicao", "justificativa"])
            writer.writeheader()
            for i, r in enumerate(ordered):
                sid = r["solicitacao_id"]
                contributions = model.features[sid] * model.representative
                top = sorted(
                    zip(CRITERIA, [sum(contributions[j : j + 2]) for j in range(0, model.nvars, 2)]),
                    key=lambda x: -x[1],
                )[:3]
                nearby = [p for p in relations if sid in (p["a"], p["b"])]
                classification = (
                    "incerta"
                    if any(p["incerto"] for p in nearby)
                    else "empate necessario"
                    if any(p["empate_necessario"] for p in nearby)
                    else "necessaria nos pares avaliados (ROR ou precedencia rigida)"
                    if nearby
                    else "sem par avaliado"
                )
                text = f"Criterios principais: {', '.join(c for c, _ in top)}. Ordem {classification}."
                if notes[sid]:
                    text += " Trava: " + ", ".join(notes[sid]) + "."
                if r["imputacoes"]:
                    text += " Dado incompleto: valores imputados identificados."
                text += f" Prioridade manual apenas informativa: {r['prioridade_regulacao']}."
                if prefs.demonstrativa:
                    text += " Parametrizacao demonstrativa, sem validacao clinica."
                writer.writerow({"solicitacao_id": sid, "posicao": i + 1, "justificativa": text})

        def save(name, value):
            (staging / name).write_text(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )

        save("relacoes.json", relations)
        save(
            "funcao_representativa.json",
            {
                "politica": POLICY_VERSION,
                "incrementos": model.representative.tolist(),
                "pesos": {
                    c: float(sum(model.representative[2 * i : 2 * i + 2])) for i, c in enumerate(CRITERIA)
                },
                "preferencias": prefs.model_dump(),
            },
        )
        save(
            "fila.json",
            [
                {
                    **r,
                    "posicao": positions[r["solicitacao_id"]],
                    "pontuacao": scores[r["solicitacao_id"]],
                    "grupo_prioridade": priority_group(r),
                }
                for r in ordered
            ],
        )
        decisions = (folder / "DECISOES.md").read_text() + "\n# Decisões de pontuação\n\n"
        decisions += "SWALIS é uma adaptação técnica das descrições do desafio: A1 para CID urgente ou oncologia com evento de piora durante espera; A2 para CID C* ou biópsia positiva; B para EVA >=7, limitação grave ou piora; C para EVA >=4 ou limitação moderada; D para demais. A classe e o prazo nao dao preferencia temporal. Exige revisão clínica.\n"
        decisions += "Comorbidades: HAS, DM e obesidade =1; cardiopatia e DPOC =2. Deterioração: internação=2, demais eventos documentados=1, relato=0.25. São aproximações demonstrativas, não escalas clínicas validadas.\n"
        decisions += "Hierarquia antes da ROR: grupo protegido antes de sem urgencia. ROR so se compara dentro do grupo. Espera nao participa de pesos, desempates, pares ou travas; desempate final por ID estavel. Comparacoes entre grupos sao precedencias, nao diferencas aditivas.\n"
        decisions += "Nós marginais 0, 0.5 e 1 nas escalas explícitas. Incerto exige reversão estrita; empate necessário é separado. Travas conflitantes impedem publicação.\n"
        decisions += "Preferências e fontes:\n```json\n" + prefs.model_dump_json(indent=2) + "\n```\n"
        (staging / "DECISOES.md").write_text(decisions)
        manifest = {
            **retention(),
            "politica": POLICY_VERSION,
            "preferencias_sha256": hashlib.sha256(prefs.model_dump_json().encode()).hexdigest(),
            "entrada_manifesto_sha256": hashlib.sha256((folder / "manifesto.json").read_bytes()).hexdigest(),
            "saida_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in staging.iterdir()},
        }
        upstream = json.loads((folder / "manifesto.json").read_text())
        if upstream.get("expira_epoch") is not None:
            if upstream["expira_epoch"] <= time.time():
                raise ValueError("Dados tratados expirados")
            manifest["expira_epoch"] = min(manifest["expira_epoch"], upstream["expira_epoch"])
        save("manifesto.json", manifest)
        protect(staging)
        staging.rename(dest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {
        "solicitacoes": len(ordered),
        "pares": len(relations),
        "incertos": sum(p["incerto"] for p in relations),
        "demonstrativa": prefs.demonstrativa,
    }
