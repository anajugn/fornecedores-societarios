"""Proxy territorial de cor/raça (RN-06) e tradução de município da Receita para o código IBGE.

Fonte: SIDRA, Censo 2022, tabela 9605, classificação 86 (Cor ou raça), nível município (N6).
Saídas em data/processed:
  municipios_cor_raca.parquet      (codigo_ibge, nome, uf, populacao, pct_*)
  municipios_receita_ibge.parquet  (cod_receita, uf, codigo_ibge) para os municípios dos fornecedores

Uso:
  python 08_proxy_racial.py --metadados   # só confere variáveis e categorias da tabela 9605
  python 08_proxy_racial.py               # baixa por UF, calcula os percentuais e traduz
"""
import argparse
import re
import sys
import time
import unicodedata

import duckdb
import pandas as pd
import requests

from config import INTERIM, PROCESSED

BASE = "https://servicodados.ibge.gov.br/api/v3/agregados/9605"
UFS = [11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29,
       31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53]
RF = INTERIM / "receita_filtrada"
NOMES = {"TOTAL": "total", "BRANCA": "branca", "PRETA": "preta", "AMARELA": "amarela",
         "PARDA": "parda", "INDIGENA": "indigena"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def get(url):
    for i in range(5):
        try:
            r = requests.get(url, timeout=120)
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


def metadados():
    m = get(f"{BASE}/metadados")
    print("tabela:", m.get("nome"))
    print("variáveis:")
    for v in m["variaveis"]:
        print(f"  {v['id']}  {v['nome']}  [{v.get('unidade')}]")
    cands = [v for v in m["variaveis"]
             if "POPULACAORESIDENTE" in norm(v["nome"]) and norm(v.get("unidade") or "") == "PESSOAS"]
    cls = next((c for c in m["classificacoes"] if str(c["id"]) == "86"), None)
    if cls is None or not cands:
        sys.exit("não achei a variável de população em pessoas ou a classificação 86: "
                 "cole a lista acima para ajustarmos")
    cats = {}
    print("categorias da classificação 86:")
    for c in cls["categorias"]:
        print(f"  {c['id']}  {c['nome']}")
        k = NOMES.get(norm(c["nome"]))
        if k and k not in cats:
            cats[k] = c["id"]
    falta = set(NOMES.values()) - set(cats)
    if falta:
        sys.exit(f"categorias não encontradas: {sorted(falta)}")
    print(f"\nusando a variável {cands[0]['id']} ({cands[0]['nome']}) e as categorias {cats}")
    return cands[0]["id"], cats


def baixar(var_id, cats):
    ids = ",".join(str(i) for i in cats.values())
    linhas = []
    for uf in UFS:
        url = (f"{BASE}/periodos/2022/variaveis/{var_id}"
               f"?localidades=N6[N3[{uf}]]&classificacao=86[{ids}]")
        dados = get(url)
        antes = len(linhas)
        for var in dados:
            for res in var["resultados"]:
                cat = next(iter(res["classificacoes"][0]["categoria"]))
                for s in res["series"]:
                    loc = s["localidade"]
                    linhas.append((str(loc["id"]), loc["nome"], str(cat), s["serie"].get("2022")))
        print(f"UF {uf}: {(len(linhas) - antes) // len(cats)} municípios", flush=True)
    return linhas


def montar(linhas, cats):
    inv = {str(v): k for k, v in cats.items()}
    df = pd.DataFrame(linhas, columns=["codigo_ibge", "nome_uf", "cat", "valor"])
    df["cat"] = df.cat.map(inv)
    df["valor"] = pd.to_numeric(df.valor, errors="coerce")        # "-" ou "X" viram nulo
    p = (df.pivot_table(index=["codigo_ibge", "nome_uf"], columns="cat", values="valor", aggfunc="first")
         .reset_index())
    p[["nome", "uf"]] = p.nome_uf.str.rsplit(" - ", n=1, expand=True)
    tot = p.total.sum()
    print(f"\nmunicípios: {len(p):,} | sem valor de população: {int(p.total.isna().sum())}")
    print(f"população total: {tot:,.0f} | Brasil: pretos e pardos {100 * (p.preta.sum() + p.parda.sum()) / tot:.1f}%"
          f", brancos {100 * p.branca.sum() / tot:.1f}%")
    p = p.rename(columns={"total": "populacao"})
    for k in ("branca", "preta", "parda", "amarela", "indigena"):
        p[f"pct_{k}"] = (100 * p[k] / p.populacao).round(2)
    p["pct_negra"] = (100 * (p.preta + p.parda) / p.populacao).round(2)    # preta + parda
    p["populacao"] = p.populacao.astype("Int64")
    return p[["codigo_ibge", "nome", "uf", "populacao", "pct_negra", "pct_branca",
              "pct_preta", "pct_parda", "pct_amarela", "pct_indigena"]]


def traduzir(ibge):
    dom = RF / "dominio_municipios.parquet"
    if not dom.exists() or not list(RF.glob("Estabelecimentos_*.parquet")):
        print("\nsem receita_filtrada: pulando a tradução de municípios (rode o 05 antes)")
        return
    con = duckdb.connect()
    est = con.execute(f"""SELECT municipio AS cod_receita, uf, count(*) AS n
                          FROM read_parquet('{(RF / "Estabelecimentos_*.parquet").as_posix()}')
                          GROUP BY 1, 2""").df()
    nomes = con.execute(f"SELECT codigo AS cod_receita, descricao FROM read_parquet('{dom.as_posix()}')").df()
    t = est.merge(nomes, on="cod_receita", how="left")
    t["chave"] = t.descricao.map(norm) + "|" + t.uf.astype(str)
    chaves = ibge.assign(chave=ibge.nome.map(norm) + "|" + ibge.uf)[["chave", "codigo_ibge"]]
    t = t.merge(chaves, on="chave", how="left")
    ok = t.codigo_ibge.notna()
    print(f"\nmunicípios dos fornecedores (pares código da Receita e UF): {len(t):,}")
    print(f"traduzidos para o código IBGE: {int(ok.sum()):,} ({ok.mean():.1%}) | "
          f"estabelecimentos cobertos: {t.n[ok].sum() / t.n.sum():.1%}")
    for r in t[~ok & (t.uf != "EX")].sort_values("n", ascending=False).head(15).itertuples():
        print(f"  sem correspondência: {r.descricao} ({r.uf}), código {r.cod_receita}, {r.n} estabelecimentos")
    t.loc[ok, ["cod_receita", "uf", "codigo_ibge"]].to_parquet(
        PROCESSED / "municipios_receita_ibge.parquet", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadados", action="store_true")
    a = ap.parse_args()
    var_id, cats = metadados()
    if a.metadados:
        return
    tab = montar(baixar(var_id, cats), cats)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    tab.to_parquet(PROCESSED / "municipios_cor_raca.parquet", index=False)
    print(f"gravado: {PROCESSED / 'municipios_cor_raca.parquet'}")
    traduzir(tab)


if __name__ == "__main__":
    main()