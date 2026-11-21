"""Verificação de saúde (workflow agendado). Só leitura: não altera nenhum dado.
Testa a resposta das APIs de origem e do banco, e grava saude.log.
Sai com código 1 se algo falhar (o workflow fica vermelho e o GitHub avisa por e-mail)."""
import os
import sys
import time
from datetime import datetime, timezone

import requests

FONTES = [
    ("PNCP, contratos", "https://pncp.gov.br/api/consulta/v1/contratos",
     {"dataInicial": "20250102", "dataFinal": "20250102", "pagina": 1, "tamanhoPagina": 10}),
    ("IBGE, nomes (v2)", "https://servicodados.ibge.gov.br/api/v2/censos/nomes/maria", None),
    ("IBGE, SIDRA 9605", "https://servicodados.ibge.gov.br/api/v3/agregados/9605/metadados", None),
]


def http(url, params, tentativas=3):
    ultimo = ""
    for i in range(tentativas):
        t = time.perf_counter()
        try:
            r = requests.get(url, params=params, timeout=60, headers={"User-Agent": "monitoramento-academico"})
            ms = (time.perf_counter() - t) * 1000
            if r.status_code in (200, 204):
                return True, f"HTTP {r.status_code} em {ms:.0f} ms"
            ultimo = f"HTTP {r.status_code} em {ms:.0f} ms: {r.text[:120]!r}"
        except requests.RequestException as e:
            ultimo = f"erro: {type(e).__name__}"
        time.sleep(2 ** i)
    return False, f"{ultimo} (após {tentativas} tentativas)"


def banco(url):
    import psycopg2
    t = time.perf_counter()
    try:
        con = psycopg2.connect(url, connect_timeout=30)
        cur = con.cursor()
        cur.execute("SELECT (SELECT count(*) FROM fato_contrato), pg_database_size(current_database())")
        n, b = cur.fetchone()
        con.close()
        return True, f"{n:,} contratos, {b / 1e6:.0f} MB, {(time.perf_counter() - t) * 1000:.0f} ms"
    except Exception as e:
        return False, f"FALHA ({type(e).__name__}): o serviço do Aiven pode estar desligado"


def main():
    linhas = [f"verificação em {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"]
    ok = True
    for nome, url, params in FONTES:
        bom, msg = http(url, params)
        ok &= bom
        linhas.append(f"{'OK   ' if bom else 'FALHA'} {nome}: {msg}")
    dburl = os.getenv("DATABASE_URL")
    if dburl:
        bom, msg = banco(dburl)
        ok &= bom
        linhas.append(f"{'OK   ' if bom else 'FALHA'} PostgreSQL (Aiven): {msg}")
    else:
        linhas.append("PULOU PostgreSQL: DATABASE_URL não definido")
    texto = "\n".join(linhas)
    print(texto)
    with open("saude.log", "w", encoding="utf-8") as f:
        f.write(texto + "\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()