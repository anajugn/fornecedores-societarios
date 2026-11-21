"""Achados de Q1, Q2 e Q3 a partir do banco, com conferência independente por SQL.
Reaproveita a camada de dados do painel (app/dados.py): os números daqui são os do painel.

Uso:  python 10_achados.py
"""
import sys

import numpy as np
import psycopg2

from config import DATABASE_URL, ROOT

sys.path.insert(0, str(ROOT / "app"))
import dados  # noqa: E402

TETO = 100_000_000
MIN_N = 5
DEF = ["feminino", "masculino"]


def pct_fem(d, por="valor"):
    dd = d[d["classe"].isin(DEF)]
    if dd["cnpj_raiz"].nunique() < MIN_N:
        return np.nan
    f = dd[dd["classe"] == "feminino"]
    return 100 * f["valor"].sum() / dd["valor"].sum() if por == "valor" else 100 * len(f) / len(dd)


def pct_forn_fem(d):
    f = d[d["classe"].isin(DEF)].drop_duplicates("cnpj_raiz")
    return 100 * (f["classe"] == "feminino").mean() if len(f) >= MIN_N else np.nan


def razao_medianas(d):
    f = d.loc[d["classe"] == "feminino", "valor"]
    m = d.loc[d["classe"] == "masculino", "valor"]
    return f.median() / m.median() if len(f) and len(m) else np.nan


def concentracao(d):
    v = d.groupby("cnpj_raiz")["valor"].sum().sort_values().to_numpy()
    n, tot = len(v), v.sum()
    gini = 2 * np.sum(np.arange(1, n + 1) * v) / (n * tot) - (n + 1) / n
    k = max(1, round(n * 0.01))
    return n, v[::-1][:10].sum() / tot, k, v[::-1][:k].sum() / tot, gini, ((v / tot) ** 2).sum() * 1e4


def main():
    if not DATABASE_URL:
        sys.exit("DATABASE_URL vazio: confira o .env")
    d, ponte = dados.banco(DATABASE_URL)
    cim = d["orgao"].str.contains("CIMINAS", na=False)
    cen = {"todos os contratos": d,
           "sem contratos acima de R$ 100 mi": d[d["valor"] <= TETO],
           "sem o CIMINAS": d[~cim],
           "sem os dois": d[(d["valor"] <= TETO) & ~cim]}

    print(f"base do painel: {len(d):,} contratos, {d['cnpj_raiz'].nunique():,} fornecedores, "
          f"R$ {d['valor'].sum() / 1e9:,.1f} bi")
    print(f"CIMINAS: {int(cim.sum()):,} contratos, {100 * d.loc[cim, 'valor'].sum() / d['valor'].sum():.1f}% do valor")

    print("\nvalor por classe de controle (todos os contratos):")
    s = d.groupby("classe")["valor"].sum()
    for c, v in (100 * s / s.sum()).items():
        print(f"  {dados.ROTULO[c]:<22}{v:5.1f}%")

    print("\n== Q1: participação feminina (só empresas de controle definido) ==")
    for nome, x in cen.items():
        print(f"{nome}: {len(x):,} contratos, R$ {x['valor'].sum() / 1e9:,.1f} bi")
        print(f"   % do valor {pct_fem(x):.1f} | % dos contratos {pct_fem(x, 'n'):.1f} | "
              f"% dos fornecedores {pct_forn_fem(x):.1f} | razão das medianas F/M {razao_medianas(x):.2f}")

    print("\n== Q2: por composição racial do município do fornecedor (proxy territorial) ==")
    for nome in ("todos os contratos", "sem contratos acima de R$ 100 mi"):
        x = cen[nome]
        x = x[x["faixa_negra"] != dados.SEM_DADO]
        print(f"{nome} ({len(x):,} contratos com município traduzido)")
        for faixa in dados.FAIXAS_NEGRA:
            g = x[x["faixa_negra"] == faixa]
            nf = g[g["classe"].isin(DEF)]["cnpj_raiz"].nunique()
            if nf < MIN_N:
                print(f"   {faixa:<14} oculta (menos de {MIN_N} fornecedores)")
                continue
            print(f"   {faixa:<14} fornecedores {nf:>6,} | % do valor feminino {pct_fem(g):5.1f} | "
                  f"razão das medianas {razao_medianas(g):.2f}")

    print("\n== Q3: concentração ==")
    for nome, x in cen.items():
        n, t10, k, t1, g, h = concentracao(x)
        print(f"{nome}: {n:,} fornecedores | 10 maiores {100 * t10:.1f}% | 1% maiores ({k}) "
              f"{100 * t1:.1f}% | Gini {g:.3f} | HHI {h:,.0f}")
    p = ponte[ponte["cnpj_raiz"].isin(set(d["cnpj_raiz"]))]
    por = p.groupby("sk_socio")["cnpj_raiz"].nunique()
    print(f"sócios elegíveis: {len(por):,} | em 2+ fornecedores: {int((por >= 2).sum()):,} "
          f"({100 * (por >= 2).mean():.1f}%) | máximo de fornecedores por sócio: {int(por.max())}")

    print("\n== conferência independente por SQL ==")
    con = psycopg2.connect(DATABASE_URL, connect_timeout=30)
    cur = con.cursor()
    cur.execute("""SELECT count(*), sum(c.valor_global),
                          sum(c.valor_global) FILTER (WHERE f.classificacao_controle = 'feminino'),
                          sum(c.valor_global) FILTER (WHERE f.classificacao_controle IN ('feminino', 'masculino'))
                   FROM fato_contrato c JOIN dim_fornecedor f ON f.cnpj_raiz = c.cnpj_raiz_fornecedor
                   WHERE c.valor_global > 0""")
    n, tot, fem, defin = cur.fetchone()
    con.close()
    sql_pct = 100 * float(fem) / float(defin)
    print(f"contratos e valor total: SQL {n:,} / R$ {float(tot):,.2f} | painel {len(d):,} / R$ {d['valor'].sum():,.2f}"
          f" -> {'confere' if n == len(d) and abs(float(tot) - d['valor'].sum()) < 1 else 'DIVERGE'}")
    print(f"% do valor feminino: SQL {sql_pct:.3f} | painel {pct_fem(d):.3f}"
          f" -> {'confere' if abs(sql_pct - pct_fem(d)) < 1e-4 else 'DIVERGE'}")


if __name__ == "__main__":
    main()