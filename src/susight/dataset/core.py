from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import unicodedata
from datetime import date
from importlib.resources import files
from pathlib import Path

REFERENCE = date(2026, 10, 23)
RULES = json.loads(files('susight.dataset').joinpath('rules.json').read_text())
LIMITATIONS = ['nenhuma', 'leve', 'moderada', 'grave']
MEASURES = {'asa': (1, 4), 'intensidade_dor_eva': (0, 10), 'distancia_hospital_km': (0, 800)}
REQUIRED = {
    'fila_cirurgica.csv': {'solicitacao_id', 'paciente_id', 'procedimento_id', 'cid_principal',
        'data_entrada_fila', 'asa', 'intensidade_dor_eva', 'limitacao_funcional',
        'distancia_hospital_km', 'justificativa_clinica', 'observacoes'},
    'eventos_clinicos.csv': {'evento_id', 'solicitacao_id', 'paciente_id', 'data_evento',
        'tipo_evento', 'resultado', 'valor_numerico', 'descricao', 'origem'},
    'procedimentos.csv': {'procedimento_id', 'procedimento', 'especialidade'},
}


def normalize(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', value.lower())
                   if unicodedata.category(c) != 'Mn')


def stable_id(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def parse_date(value):
    try:
        return date.fromisoformat(value) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) else None
    except (ValueError, TypeError):
        return None


def read_inputs(folder: Path):
    tables, hashes = {}, {}
    for name in [*REQUIRED, 'README.md', 'dicionario_dados.md']:
        path = folder / name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if name not in REQUIRED:
            continue
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not REQUIRED[name].issubset(reader.fieldnames or []):
                raise ValueError(f'{name}: colunas obrigatorias ausentes')
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError(f'{name}: colunas repetidas')
            key = next(k for k in ['solicitacao_id', 'evento_id', 'procedimento_id']
                       if k in REQUIRED[name] and (k == 'evento_id' if name.startswith('eventos') else
                           k == 'procedimento_id' if name.startswith('procedimentos') else k == 'solicitacao_id'))
            unique = {}
            for row in reader:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f'{name}: linha malformada {reader.line_num}')
                if not row[key].strip():
                    raise ValueError(f'{name}: identificador vazio {reader.line_num}')
                origin = {'arquivo': name, 'linha': reader.line_num}
                if row[key] in unique:
                    if unique[row[key]]['raw'] != row:
                        raise ValueError(f'{name}: identificador conflitante {row[key]}')
                    unique[row[key]]['origens'].append(origin)
                else:
                    unique[row[key]] = {'raw': row, 'origens': [origin]}
            tables[name] = list(unique.values())
    return tables, hashes


def normalize_request(source, catalog, reference=REFERENCE):
    raw = source['raw']
    n = {k: v.strip() for k, v in raw.items()}
    issues, pending = [], []
    cid = re.sub(r'[.\s]', '', n['cid_principal']).upper()
    n['cid'] = cid if re.fullmatch(r'[A-Z][0-9]{2}[0-9A-Z]{0,2}', cid) else None
    if n['cid'] is None:
        pending.append('cid_invalido_ou_ausente')
    n['oncologico_por_cid'] = n['cid'].startswith('C') if n['cid'] else None
    n['prioridade_regulacao'] = normalize(n.get('prioridade_regulacao', '')) or None
    if n['prioridade_regulacao'] not in {'alta', 'media', 'baixa', None}:
        issues.append('prioridade_invalida')
        n['prioridade_regulacao'] = None
    n['municipio'] = ' '.join(normalize(n.get('municipio', '')).split()).title()
    proc = catalog.get(n['procedimento_id'])
    if proc:
        for k in ['procedimento', 'especialidade']:
            if normalize(n.get(k, '')) != normalize(proc[k]):
                issues.append(f'divergencia_catalogo:{k}')
            n[k] = proc[k]
    else:
        pending.append('procedimento_desconhecido')
    entered = parse_date(n['data_entrada_fila'])
    if not entered or entered > reference:
        pending.append('data_entrada_invalida')
        n['dias_em_fila'] = None
    else:
        n['dias_em_fila'] = (reference - entered).days
        if str(n['dias_em_fila']) != raw.get('dias_em_fila'):
            issues.append('espera_recalculada')
    measures = {}
    for key, (low, high) in MEASURES.items():
        try:
            number = float(n[key])
            if not math.isfinite(number) or not low <= number <= high or not number.is_integer():
                raise ValueError
            measures[key] = int(number)
        except (ValueError, TypeError):
            measures[key] = None
            issues.append(f'ausente_ou_invalido:{key}')
    lim = normalize(n['limitacao_funcional'])
    measures['limitacao_funcional'] = lim if lim in LIMITATIONS else None
    if measures['limitacao_funcional'] is None:
        issues.append('ausente_ou_invalido:limitacao_funcional')
    return {'solicitacao_id': raw['solicitacao_id'], 'paciente_id': raw['paciente_id'],
            'aliases': [], 'originais': [source], 'normalizado': n, 'medidas_observadas': measures,
            'medidas_pontuacao': measures.copy(), 'estado': 'pendente' if pending else 'ativa',
            'avisos': issues, 'pendencias': pending, 'evidencias_ids': [], 'imputacoes': [], 'eventos': []}


def extract(text, source):
    # NFD accent removal preserves code-point length for the dataset's Latin characters.
    normalized = normalize(text)
    evidence = []
    for concept, pattern in RULES['concepts'].items():
        for match in re.finditer(pattern, normalized):
            left = max(normalized.rfind(p, 0, match.start()) for p in '.;!?\n') + 1
            prefix = normalized[left:match.start()][-70:]
            suffix = normalized[match.end():match.end()+45].split('.')[0]
            clause = prefix + match.group() + suffix
            negative = re.search(r'\b(?:' + RULES['negation'] + r')\b', prefix)
            uncertain = re.search(RULES['uncertainty'], clause)
            if concept == 'cirurgia_outro_servico' and not re.search(r'realizad|operad|operou|ja fez|foi submetid', clause):
                uncertain = True
            polar = 'negada' if negative else 'incerta' if uncertain else 'afirmada'
            item = {**source, 'conceito': concept, 'trecho': text[match.start():match.end()],
                    'inicio': match.start(), 'fim': match.end(), 'polaridade': polar,
                    'natureza': 'indicio_textual', 'regra': concept, 'versao': RULES['version']}
            item['evidencia_id'] = stable_id(item)
            evidence.append(item)
    return evidence


def consolidate(requests):
    groups = {}
    aliases = {r['solicitacao_id']: r['solicitacao_id'] for r in requests}
    for r in requests:
        n = r['normalizado']
        groups.setdefault((r['paciente_id'], n['procedimento_id']), []).append(r)
    output = []
    for group in groups.values():
        if len(group) == 1:
            output.extend(group)
            continue
        contexts = [(' '.join(normalize(r['normalizado']['justificativa_clinica']).split()),
                     ' '.join(normalize(r['normalizado']['observacoes']).split())) for r in group]
        known = all(re.search(r'hernia|colelit|catarata|artrose|neoplas|tumor|variz|varizes|carcinoma|tunel', c[0]) for c in contexts)
        forbidden = any(re.search(r'novo episodio|nova indicacao|recidiva|reativ|outro episodio', ' '.join(c)) for c in contexts)
        compatible = (known and not forbidden and len(set(contexts)) == 1
                      and len({r['normalizado']['cid'] for r in group}) == 1
                      and all(not r['pendencias'] for r in group)
                      and all(r['medidas_observadas'] == group[0]['medidas_observadas'] for r in group))
        if not compatible:
            for r in group:
                r['avisos'].append('duplicata_possivel_revisar')
            output.extend(group)
            continue
        group.sort(key=lambda r: (r['normalizado']['data_entrada_fila'], r['solicitacao_id']))
        canonical = group[0]
        for alias in group[1:]:
            aliases[alias['solicitacao_id']] = canonical['solicitacao_id']
            canonical['aliases'].append(alias['solicitacao_id'])
            canonical['originais'].extend(alias['originais'])
            canonical['evidencias_ids'].extend(alias['evidencias_ids'])
        output.append(canonical)
    return sorted(output, key=lambda r: r['solicitacao_id']), aliases
