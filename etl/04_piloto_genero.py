"""T3/S2: piloto de inferência de gênero (RN-04) em 1.000 sócios pessoa física.
Fonte: API de nomes do IBGE v2 (Censo 2010). Imprime só agregados, nunca nomes."""
import itertools
import json
import re
import time
import unicodedata
from collections import Counter

import pandas as pd
import requests

from config import INTERIM, LIMIAR_GENERO, url_receita
from receita_stream import COLUNAS, registros_zip

N_LINHAS, N_PILOTO, SEMENTE, LOTE = 200_000, 1_000, 42, 20
API = "https://servicodados.ibge.gov.br/api/v2/censos/nomes/"
CACHE = INTERIM / "cache_nomes_ibge.json"      # dentro de data/: fora do Git
ESTADO = {"lote": True}                        # vira False se a API recusar vários nomes por chamada


def primeiro_nome(nome):
    s = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().upper()
    partes = re.sub(r"[^A-Z ]", " ", s).split()
    return partes[0] if partes else ""


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
    if ESTADO["lote"] and len(nomes) > 1:
        try:
            return _consultar(nomes, sexo)
        except (requests.RequestException, ValueError):
            ESTADO["lote"] = False
            print("  (a API não aceitou vários nomes por chamada: passando a um nome por chamada)")
    saida = {}
    for n in nomes:
        saida.update(_consultar([n], sexo))
        time.sleep(0.2)
    return saida


def amostra():
    rows = list(itertools.islice(
        registros_zip(url_receita("Socios0.zip"), len(COLUNAS["Socios"])), N_LINHAS))
    df = pd.DataFrame(rows, columns=COLUNAS["Socios"])
    pf = df[(df.identificador_socio == "2") & (df.nome_socio.str.strip() != "")]
    nomes = pf.sample(N_PILOTO, random_state=SEMENTE)["nome_socio"].map(primeiro_nome)
    return nomes[nomes != ""]


def classificar(nome, cache, limiar):
    c = cache.get(nome, {"F": 0, "M": 0})
    total = c["F"] + c["M"]
    if total == 0:
        return "I_ausente"                    # nome fora da base ou suprimido pelo IBGE
    if max(c["F"], c["M"]) / total < limiar:
        return "I_ambiguo"
    return "F" if c["F"] > c["M"] else "M"


if __name__ == "__main__":
    pessoas = amostra()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    novos = sorted(set(pessoas) - set(cache))
    chamadas = 0
    for i in range(0, len(novos), LOTE):
        lote = novos[i:i + LOTE]
        f, m = consultar(lote, "F"), consultar(lote, "M")
        chamadas += 1
        for n in lote:
            cache[n] = {"F": f[n], "M": m[n]}
        CACHE.write_text(json.dumps(cache), encoding="utf-8")   # salva a cada lote: dá para retomar
        time.sleep(0.3)

    modo = "vários nomes por chamada" if ESTADO["lote"] else "um nome por chamada"
    print(f"sócios PF sorteados: {len(pessoas)} | primeiros nomes distintos: {pessoas.nunique()}")
    print(f"consultados na API agora: {len(novos)} nomes ({modo}); o resto veio do cache")

    total = len(pessoas)
    cont = Counter(classificar(n, cache, LIMIAR_GENERO) for n in pessoas)
    print(f"\n--- limiar {LIMIAR_GENERO:.0%} ---")
    for k in ("F", "M", "I_ambiguo", "I_ausente"):
        print(f"  {k:<10} {cont[k]:>5}  {cont[k] / total:6.1%}")
    ind = cont["I_ambiguo"] + cont["I_ausente"]
    print(f"  classificados: {1 - ind / total:.1%} | indeterminados: {ind / total:.1%}")

    print("\n--- sensibilidade ao limiar (% de indeterminados) ---")
    for t in (0.80, 0.90, 0.95, 0.99):
        c = Counter(classificar(n, cache, t) for n in pessoas)
        print(f"  {t:.0%}: {(c['I_ambiguo'] + c['I_ausente']) / total:.1%}")