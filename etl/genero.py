"""Inferência de gênero pelo primeiro nome (RN-04): API de nomes do IBGE v2 (Censo 2010), com cache em disco."""
import json
import re
import time
import unicodedata

import requests

from config import INTERIM

API = "https://servicodados.ibge.gov.br/api/v2/censos/nomes/"
CACHE = INTERIM / "cache_nomes_ibge.json"      # dentro de data/: fora do Git
LOTE = 20
_ESTADO = {"lote": True}                       # vira False se a API recusar vários nomes por chamada


def normalizar_nome(nome):
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().upper()
    return " ".join(re.sub(r"[^A-Z ]", " ", s).split())


def primeiro_nome(nome):
    n = normalizar_nome(nome)
    return n.split()[0] if n else ""


def carregar_cache():
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def _get(url, params):
    for i in range(5):
        try:
            r = requests.get(url, params=params, timeout=60)
        except requests.RequestException:
            if i == 4:
                raise
            time.sleep(2 ** i)
            continue
        if r.status_code in (429, 500, 502, 503, 504) and i < 4:
            time.sleep(2 ** i)
            continue
        r.raise_for_status()
        return r.json()


def _consultar(nomes, sexo):
    dados = _get(API + "|".join(nomes), {"sexo": sexo})
    if not isinstance(dados, list):
        raise ValueError("resposta inesperada da API")
    saida = {n: 0 for n in nomes}
    for item in dados:
        n = str(item.get("nome", "")).upper()
        if n in saida:
            saida[n] = sum(p.get("frequencia", 0) for p in item.get("res", []))
    return saida


def consultar(nomes, sexo):
    if _ESTADO["lote"] and len(nomes) > 1:
        try:
            return _consultar(nomes, sexo)
        except (requests.RequestException, ValueError):
            _ESTADO["lote"] = False
            print("  (a API não aceitou vários nomes por chamada: passando a um nome por chamada)")
    saida = {}
    for n in nomes:
        saida.update(_consultar([n], sexo))
        time.sleep(0.2)
    return saida


def completar_cache(nomes, cache):
    """Consulta só os nomes que faltam no cache; salva a cada lote (dá para retomar)."""
    faltam = sorted(set(nomes) - set(cache))
    for k, i in enumerate(range(0, len(faltam), LOTE), start=1):
        lote = faltam[i:i + LOTE]
        f, m = consultar(lote, "F"), consultar(lote, "M")
        for n in lote:
            cache[n] = {"F": f[n], "M": m[n]}
        CACHE.write_text(json.dumps(cache), encoding="utf-8")
        if k % 20 == 0:
            print(f"  nomes consultados: {min(i + LOTE, len(faltam)):,} de {len(faltam):,}", flush=True)
        time.sleep(0.3)
    return len(faltam)


def _totais(nome, cache):
    c = cache.get(nome, {"F": 0, "M": 0})
    return c["F"], c["M"]


def classificar(nome, cache, limiar):
    f, m = _totais(nome, cache)
    total = f + m
    if total == 0:
        return "I_ausente"                     # nome fora da base ou suprimido pelo IBGE
    if max(f, m) / total < limiar:
        return "I_ambiguo"
    return "F" if f > m else "M"


def confianca(nome, cache):
    f, m = _totais(nome, cache)
    total = f + m
    return max(f, m) / total if total else 0.0