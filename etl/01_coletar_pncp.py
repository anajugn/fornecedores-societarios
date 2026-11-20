"""Coleta contratos do PNCP, um arquivo NDJSON por dia. Retomável."""
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import requests
from config import DATA_FIM, DATA_INI, PNCP_PARALELO, PNCP_PAUSA_S, PNCP_URL, RAW_PNCP

S = requests.Session()
S.headers["Accept"] = "application/json"


def get(params, tentativas=8):
    ultimo = None
    for i in range(tentativas):
        try:
            r = S.get(PNCP_URL, params=params, timeout=60)
            if r.status_code == 204:
                return None
            if r.status_code == 200:
                return r.json()
            if r.status_code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            ultimo = f"HTTP {r.status_code}"
        except requests.RequestException as e:   # DNS, conexão encerrada, timeout
            ultimo = repr(e)
        time.sleep(min(2 ** i * 2, 120))
    raise RuntimeError(f"falhou após {tentativas} tentativas: {ultimo}")


def coletar_dia(d):
    destino = RAW_PNCP / f"{d.isoformat()}.ndjson"
    if destino.exists():
        return d, "pulado", 0, 0
    tmp = destino.with_suffix(".tmp")
    ds = d.strftime("%Y%m%d")
    pagina, total, esperado = 1, 0, 0
    try:
        with tmp.open("w", encoding="utf-8") as f:
            while True:
                j = get({"dataInicial": ds, "dataFinal": ds,
                         "pagina": pagina, "tamanhoPagina": 500})
                if not j or not j.get("data"):
                    break
                esperado = j.get("totalRegistros", esperado)
                for reg in j["data"]:
                    f.write(json.dumps(reg, ensure_ascii=False) + "\n")
                    total += 1
                if pagina >= j.get("totalPaginas", 1):
                    break
                pagina += 1
                time.sleep(PNCP_PAUSA_S)
        tmp.rename(destino)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return d, "ok", total, esperado


def main():
    dias, d = [], DATA_INI
    while d <= DATA_FIM:
        dias.append(d)
        d += timedelta(days=1)

    falhas = []
    with ThreadPoolExecutor(PNCP_PARALELO) as ex:
        futs = {ex.submit(coletar_dia, d): d for d in dias}
        for fut in as_completed(futs):
            d = futs[fut]
            try:
                _, st, n, esp = fut.result()
                aviso = "  <-- COBERTURA DIVERGE" if st == "ok" and n != esp else ""
                print(f"{d} {st} {n}/{esp}{aviso}", flush=True)
            except Exception as e:
                falhas.append(d)
                print(f"{d} FALHOU: {e}", flush=True)
    print(f"\nconcluído. falhas: {len(falhas)} -> rode de novo para refazer só elas")


if __name__ == "__main__":
    main()