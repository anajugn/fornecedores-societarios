"""T2/T3: a mesma análise em Pandas (arquivos locais) e em PostgreSQL (Aiven).

Rode depois da carga (07) e com os mesmos arquivos de data/ que foram carregados.
Cria os agregados de sql/agregados.sql, confere se os resultados batem e mede os tempos.
Grava docs/teste_comparativo.md.

Uso:  python 09_teste_comparativo.py [--rep 7]
"""
import argparse
import math
import statistics
import sys
import time

import pandas as pd
import psycopg2

from config import DATA_FIM, DATA_INI, DATABASE_URL, INTERIM, PROCESSED, ROOT

REC = INTERIM / "contratos_recorte.parquet"
EMP = PROCESSED / "empresas_classificadas.parquet"
SOC = PROCESSED / "socios_classificados.parquet"
AGREGADOS = ROOT / "etl" / "sql" / "agregados.sql"
SAIDA = ROOT / "docs" / "teste_comparativo.md"

SQL = {
    "A": """SELECT f.classificacao_controle, count(*), sum(c.valor_global)
            FROM fato_contrato c JOIN dim_fornecedor f ON f.cnpj_raiz = c.cnpj_raiz_fornecedor
            WHERE c.valor_global > 0 GROUP BY 1""",
    "B": """WITH forn AS (SELECT DISTINCT cnpj_raiz_fornecedor AS r FROM fato_contrato
                         WHERE cnpj_raiz_fornecedor IS NOT NULL AND valor_global > 0),
                 p AS (SELECT sk_socio, count(DISTINCT cnpj_raiz) AS n FROM ponte_empresa_socio
                       WHERE elegivel AND cnpj_raiz IN (SELECT r FROM forn) GROUP BY 1)
            SELECT count(*), count(*) FILTER (WHERE n >= 2) FROM p""",
    "C": """SELECT c.cnpj_raiz_fornecedor, sum(c.valor_global) AS v
            FROM fato_contrato c JOIN dim_fornecedor f ON f.cnpj_raiz = c.cnpj_raiz_fornecedor
            WHERE c.valor_global > 0 GROUP BY 1 ORDER BY v DESC, 1 LIMIT 10""",
}
MV = {
    "A": "SELECT classe, n_contratos, valor_total FROM mv_valor_por_classe",
    "B": """SELECT sum(n_socios), sum(n_socios) FILTER (WHERE n_fornecedores_do_socio >= 2)
            FROM mv_socios_compartilhados""",
    "C": """SELECT cnpj_raiz, valor_total FROM mv_fornecedor_valor
            ORDER BY valor_total DESC, cnpj_raiz LIMIT 10""",
}
NOMES = {"A": "A. valor por classe de controle (junção de 2 tabelas)",
         "B": "B. sócios em 2+ fornecedores (junção N:N pela ponte)",
         "C": "C. 10 maiores fornecedores (agregação)"}


# ------------------------------------------------------------------ Pandas
def carregar():
    c = pd.read_parquet(REC, columns=["cnpj_raiz_fornecedor", "valor_global", "data_assinatura"])
    e = pd.read_parquet(EMP, columns=["cnpj_basico", "classificacao_controle"])
    s = pd.read_parquet(SOC, columns=["cnpj_basico", "id_derivado", "elegivel"])
    return c, e, s


def base(c):
    d = pd.to_datetime(c["data_assinatura"])
    c = c[d.between(pd.Timestamp(DATA_INI), pd.Timestamp(DATA_FIM)) & c["cnpj_raiz_fornecedor"].notna()].copy()
    c["valor"] = pd.to_numeric(c["valor_global"], errors="coerce")
    return c[c["valor"] > 0]


def pandas_a(c, e, s):
    b = base(c).merge(e, left_on="cnpj_raiz_fornecedor", right_on="cnpj_basico")
    g = b.groupby("classificacao_controle")["valor"].agg(["size", "sum"])
    return {k: (int(n), float(v)) for k, n, v in zip(g.index, g["size"], g["sum"])}


def pandas_b(c, e, s):
    raizes = set(base(c)["cnpj_raiz_fornecedor"]) & set(e["cnpj_basico"])
    el = s[s["elegivel"].fillna(False).astype(bool) & s["cnpj_basico"].isin(raizes)]
    por = el.drop_duplicates(["cnpj_basico", "id_derivado"]).groupby("id_derivado").size()
    return (len(por), int((por >= 2).sum()))


def pandas_c(c, e, s):
    b = base(c).merge(e[["cnpj_basico"]], left_on="cnpj_raiz_fornecedor", right_on="cnpj_basico")
    g = b.groupby("cnpj_raiz_fornecedor")["valor"].sum().reset_index()
    g = g.sort_values(["valor", "cnpj_raiz_fornecedor"], ascending=[False, True]).head(10)
    return [(r, float(v)) for r, v in zip(g["cnpj_raiz_fornecedor"], g["valor"])]


PANDAS = {"A": pandas_a, "B": pandas_b, "C": pandas_c}


# ------------------------------------------------------------------ PostgreSQL
def canon(chave, linhas):
    if chave == "A":
        return {r[0]: (int(r[1]), float(r[2])) for r in linhas}
    if chave == "B":
        return (int(linhas[0][0]), int(linhas[0][1]))
    return [(str(r[0]).strip(), float(r[1])) for r in linhas]


def consulta_pg(con, sql, chave):
    def f():
        cur = con.cursor()
        cur.execute(sql)
        linhas = cur.fetchall()
        cur.close()
        return canon(chave, linhas)
    return f


# ------------------------------------------------------------------ medição
def medir(fn, rep):
    fn()                                         # aquecimento, descartado
    tempos, res = [], None
    for _ in range(rep):
        t = time.perf_counter()
        res = fn()
        tempos.append(time.perf_counter() - t)
    return statistics.median(tempos), res


def igual(a, b):
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(igual(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(igual(x, y) for x, y in zip(a, b))
    try:
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=0.5)
    except (TypeError, ValueError):
        return a == b


def ms(s):
    return f"{s * 1000:,.1f} ms".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rep", type=int, default=5)
    a = ap.parse_args()

    for p in (REC, EMP, SOC, AGREGADOS):
        if not p.exists():
            sys.exit(f"não achei {p}")
    if not DATABASE_URL:
        sys.exit("DATABASE_URL vazio: confira o .env")

    con = psycopg2.connect(DATABASE_URL, connect_timeout=30)
    con.autocommit = True
    cur = con.cursor()

    t = time.perf_counter()
    cur.execute(AGREGADOS.read_text(encoding="utf-8"))
    t_agreg = time.perf_counter() - t
    cur.execute("""SELECT sum(pg_total_relation_size(c.oid)) FROM pg_class c
                   WHERE c.relkind = 'm' AND c.relname LIKE 'mv\\_%'""")
    mb_agreg = float(cur.fetchone()[0] or 0) / 1e6
    print(f"agregados criados em {t_agreg:.1f} s ({mb_agreg:.2f} MB)")

    
    ping, _ = medir(consulta_pg(con, "SELECT 1", "B_ping") if False else (lambda: (cur.execute("SELECT 1"), cur.fetchall())), 15)
    print(f"latência do banco (SELECT 1): {ms(ping)}")

    t = time.perf_counter()
    mem = carregar()
    t_carga = time.perf_counter() - t
    print(f"leitura dos 3 Parquet: {t_carga:.2f} s\n")

    linhas, ok = [], True
    for k in "ABC":
        res = {}
        tempos = {}
        tempos["Pandas (lê Parquet + calcula)"], res["p1"] = medir(lambda k=k: PANDAS[k](*carregar()), a.rep)
        tempos["Pandas (já em memória)"], res["p2"] = medir(lambda k=k: PANDAS[k](*mem), a.rep)
        tempos["PostgreSQL (junções nas tabelas)"], res["pg1"] = medir(consulta_pg(con, SQL[k], k), a.rep)
        tempos["PostgreSQL (agregado materializado)"], res["pg2"] = medir(consulta_pg(con, MV[k], k), a.rep)
        confere = all(igual(res["p2"], res[x]) for x in ("p1", "pg1", "pg2"))
        ok &= confere
        print(f"{NOMES[k]}  -> resultados {'conferem' if confere else 'DIVERGEM'}")
        if not confere:
            for x, v in res.items():
                print(f"   {x}: {str(v)[:300]}")
        for metodo, s in tempos.items():
            print(f"   {metodo:<40} {ms(s):>14}")
        linhas.append((NOMES[k], confere, tempos))
    con.close()

    md = [f"# Teste comparativo: Pandas x PostgreSQL ({a.rep} repetições, mediana)\n",
          f"Latência do banco (`SELECT 1`): {ms(ping)}. Leitura dos 3 Parquet: {t_carga:.2f} s. "
          f"Criação dos agregados: {t_agreg:.1f} s ({mb_agreg:.2f} MB).\n",
          "| Consulta | Resultados conferem | " + " | ".join(linhas[0][2]) + " |",
          "|---|---|" + "---|" * len(linhas[0][2])]
    for nome, confere, tempos in linhas:
        md.append(f"| {nome} | {'sim' if confere else 'NÃO'} | " + " | ".join(ms(v) for v in tempos.values()) + " |")
    SAIDA.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\ngravado: {SAIDA}")
    if not ok:
        sys.exit("há consultas com resultados divergentes: investigue antes de citar os tempos")


if __name__ == "__main__":
    main()