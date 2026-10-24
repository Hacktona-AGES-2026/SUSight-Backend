from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AGENTS = ("evidencias", "contestacao", "equidade")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class QueuePatient(Strict):
    solicitacao_id: str = Field(min_length=1, max_length=100)
    paciente_id: str | None = None
    cid: str = Field(pattern=r"^[A-Z][0-9]{2}[0-9A-Z]{0,2}$")
    dias_em_fila: int = Field(ge=0)
    pontuacao: float = Field(ge=0, le=1)
    oncologico: bool
    sem_urgencia: bool
    sem_urgencia_verificador: bool = False
    posicao: int = Field(ge=1)

    @model_validator(mode="after")
    def cid_flag(self):
        if self.oncologico != self.cid.startswith("C") or (
            self.oncologico and (self.sem_urgencia or self.sem_urgencia_verificador)
        ):
            raise ValueError("Indicador oncologico inconsistente com CID")
        return self


class Evidence(Strict):
    evidencia_id: str = Field(min_length=1, max_length=100)
    tipo: Literal[
        "biopsia",
        "exame_imagem",
        "pronto_socorro",
        "internacao",
        "consulta_reavaliacao",
        "relato",
        "imputacao",
        "criterio",
    ]
    resultado: Literal[
        "positivo",
        "negativo",
        "inconclusivo",
        "progressao",
        "estavel",
        "piora",
        "melhora",
        "atendimento",
        "observado",
        "imputado",
        "relatado",
    ]
    data: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @model_validator(mode="after")
    def valid_date(self):
        from datetime import date

        date.fromisoformat(self.data)
        return self


class ProposalInput(Strict):
    solicitacao_id: str = Field(min_length=1, max_length=100)
    posicao_proposta: int = Field(ge=1)
    versao_fila: int = Field(ge=1)
    ordenacao_incerta: bool = False
    evidencias_conflitantes: bool = False
    evidencias: list[Evidence] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def eligible(self):
        if not self.ordenacao_incerta and not self.evidencias_conflitantes:
            raise ValueError("Tribunal exige ordenacao incerta ou evidencias conflitantes")
        if len({e.evidencia_id for e in self.evidencias}) != len(self.evidencias):
            raise ValueError("IDs de evidencia repetidos")
        return self


class Vote(Strict):
    agente: Literal["evidencias", "contestacao", "equidade"]
    veredito: Literal["a_favor", "contra", "ajustar"]
    posicao_sugerida: int | None = Field(default=None, ge=1)
    justificativa: str = Field(min_length=10, max_length=2000)
    evidencias_citadas: list[str] = Field(max_length=100)
    sem_comprovacao: bool

    @model_validator(mode="after")
    def position(self):
        if self.veredito == "ajustar" and self.posicao_sugerida is None:
            raise ValueError("Ajustar exige posicao sugerida")
        if self.veredito != "ajustar" and self.posicao_sugerida is not None:
            raise ValueError("Posicao sugerida so e permitida para ajustar")
        return self


class DocumentInput(Strict):
    solicitacao_id: str = Field(min_length=1, max_length=100)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tipo_mime: Literal["application/pdf", "image/jpeg", "image/png"]
    paginas: int = Field(ge=1, le=10)
    tamanho_bytes: int = Field(gt=0, le=10 * 1024 * 1024)
    sintetico: Literal[True]

    @model_validator(mode="after")
    def image_page(self):
        if self.tipo_mime != "application/pdf" and self.paginas != 1:
            raise ValueError("Uma imagem corresponde a uma pagina")
        return self


class EvidenceRegistration(Strict):
    evidencia: Evidence
    documento_id: str
    pagina: int = Field(ge=1, le=10)
    trecho: str = Field(min_length=1, max_length=2000)
    campo: Literal[
        "limitacao_funcional",
        "asa",
        "dor",
        "questoes_socioeconomicas",
        "comorbidades",
        "tipo_documento",
        "data_documento",
    ]
    valor: str | int | float | list[str] | None
    confianca: Literal["alta", "media", "baixa"]


class EvidenceReview(Strict):
    acao: Literal["aprovar", "rejeitar"]
    justificativa: str = Field(min_length=3, max_length=2000)

    @field_validator("justificativa")
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Justificativa obrigatoria")
        return value.strip()


class EvidenceReferences(Strict):
    solicitacao_id: str
    posicao_proposta: int = Field(ge=1)
    versao_fila: int = Field(ge=1)
    ordenacao_incerta: bool = False
    evidencias_conflitantes: bool = False
    evidencias_ids: list[str] = Field(default_factory=list, max_length=100)


class Cancellation(Strict):
    justificativa: str = Field(min_length=3, max_length=2000)

    @field_validator("justificativa")
    @classmethod
    def meaningful_reason(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Justificativa obrigatoria")
        return value.strip()
