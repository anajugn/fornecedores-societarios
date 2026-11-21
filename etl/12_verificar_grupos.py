"""Os grupos de valor repetido são o mesmo teto replicado ou contratos legítimos?
Grupo = mesmo órgão e mesmo valor (>= R$ 10 mi) em 3+ fornecedores diferentes.
Mede quantos objetos distintos há em cada grupo (objeto igual = indício de teto replicado).

Uso:  python 12_verificar_grupos.py
"""
import re
import unicodedata

import numpy as np
import pandas as pd

from config import INTERIM

MIN_VALOR, MIN_FORN, TOP = 1e7, 3, 20


def norm(texto):
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\[[^\]]*\]", " ", s)                  # tira prefixos como [Publicenter]
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", s).split())[:100]


def main():
    c = pd.read_parquet(INTERIM / "contratos_recorte.parquet")
    c = c[c["cnpj_raiz_fornecedor"].notna()].copy()
    c["v"] = pd.to_numeric(c["valor_global"], errors="coerce")
    c["obj"] = c["objeto_contrato"].map(norm)
    total = c["v"].sum()

    g = (c[c["v"] >= MIN_VALOR].groupby(["orgao_razao_social", "v"])
           .agg(contratos=("v", "size"), fornecedores=("cnpj_raiz_fornecedor", "nunique"),
                objetos=("obj", "nunique")).reset_index())
    g = g[g["fornecedores"] >= MIN_FORN].copy()
    g["valor_somado"] = g["v"] * g["contratos"]
    g["leitura"] = np.select([g["objetos"] == 1, g["objetos"] <= 3],
                             ["objeto idêntico", "objetos quase iguais"], default="objetos diferentes")

    print(f"grupos com {MIN_FORN}+ fornecedores e valor >= R$ {MIN_VALOR / 1e6:.0f} mi: {len(g)}")
    r = g.groupby("leitura").agg(grupos=("v", "size"), contratos=("contratos", "sum"),
                                 valor_bi=("valor_somado", lambda s: s.sum() / 1e9))
    r["pct_do_valor"] = 100 * r["valor_bi"] * 1e9 / total
    print(r.round(1).to_string())

    g["orgao"] = g["orgao_razao_social"].str[:48]
    print(f"\nos {TOP} maiores grupos:")
    print(g.sort_values("valor_somado", ascending=False).head(TOP)
           [["orgao", "v", "contratos", "fornecedores", "objetos", "leitura"]].to_string(index=False))

    dif = g[g["leitura"] == "objetos diferentes"].sort_values("valor_somado", ascending=False).head(3)
    for t in dif.itertuples():
        x = c[(c["orgao_razao_social"] == t.orgao_razao_social) & (c["v"] == t.v)]
        print(f"\n{t.orgao} | R$ {t.v:,.2f} | {t.contratos} contratos, {t.objetos} objetos distintos. Exemplos:")
        for o in x["obj"].drop_duplicates().head(4):
            print("   -", o[:90])


if __name__ == "__main__":
    main()