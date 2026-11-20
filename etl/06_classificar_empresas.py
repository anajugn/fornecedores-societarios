"""Fase 2: RN-03, RN-04 e RN-05 sobre a Receita filtrada.
Lê data/interim/receita_filtrada. Escreve em data/processed:
  socios_classificados.parquet   (sem nome e sem CPF: id derivado, tipo, gênero, vínculo)
  empresas_classificadas.parquet (classificação de controle por raiz de CNPJ)
O nome do sócio só existe em memória neste script (RN-09).

Uso:
  python 06_classificar_empresas.py
  python 06_classificar_empresas.py --excluir-administradores   # RN-03 estrita: Diretor, Presidente e
                                                                # Conselheiro não contam como sócios
"""
import argparse
import hashlib
import os
import re
import sys
import unicodedata

import duckdb
import numpy as np
import pandas as pd

from config import INTERIM, LIMIAR_GENERO, PROCESSED
from genero import (carregar_cache, classificar, completar_cache, confianca,
                    normalizar_nome, primeiro_nome)

RF = INTERIM / "receita_filtrada"
TIPO = {"1": "PJ", "2": "PF", "3": "ES"}
EXCLUIR = re.compile(r"\b(PROCURADOR|REPRESENTANTE|INVENTARIANTE|LIQUIDANTE|INTERVENTOR|TUTOR|CURADOR|MAE|PAI)\b")
ADMIN = re.compile(r"\b(DIRETOR|PRESIDENTE|CONSELHEIRO)\b|^ADMINISTRADOR$")
ROTULOS = [
    ("maioria_m", "masculino, por maioria dos sócios"),
    ("maioria_f", "feminino, por maioria dos sócios"),
    ("sem_maioria", "misto/indeterminado: sem maioria"),
    ("socio_pj", "misto/indeterminado: com sócio PJ"),
    ("indeterminados", "misto/indeterminado: mais de 1/3 indeterminados"),
    ("sem_socio", "sem sócio elegível"),
]


def sem_acento(s):
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()


def ler(padrao):
    if not list(RF.glob(padrao)):
        sys.exit(f"nenhum arquivo {padrao} em {RF}: rode 05_filtrar_receita.py antes")
    con = duckdb.connect()
    return con.execute(f"SELECT * FROM read_parquet('{(RF / padrao).as_posix()}')").df()


def classificar_empresas(empresas, socios, el):
    """RN-05. `el` marca os vínculos elegíveis (RN-03)."""
    base = pd.DataFrame(index=pd.Index(empresas.cnpj_basico.unique(), name="cnpj_basico"))
    base["n_socios_total"] = socios.groupby("cnpj_basico").size().reindex(base.index).fillna(0).astype(int)
    base["tem_socio_pj"] = (socios[socios.tipo == "PJ"].groupby("cnpj_basico").size()
                            .reindex(base.index).fillna(0) > 0)
    cont = (socios[el].groupby(["cnpj_basico", "genero"]).size().unstack(fill_value=0)
            .reindex(columns=["F", "M", "I"], fill_value=0).reindex(base.index, fill_value=0))
    n = cont.sum(axis=1)
    base["n_f"], base["n_m"], base["n_i"] = cont["F"], cont["M"], cont["I"]
    base["n_socios_elegiveis"] = n
    base["pct_indeterminados"] = (100 * cont["I"] / n.where(n > 0, 1)).round(2)
    base["motivo"] = np.select(
        [base.tem_socio_pj.to_numpy(), (n == 0).to_numpy(), (3 * cont["I"] > n).to_numpy(),
         (2 * cont["F"] > n).to_numpy(), (2 * cont["M"] > n).to_numpy()],
        ["socio_pj", "sem_socio", "indeterminados", "maioria_f", "maioria_m"], default="sem_maioria")
    base["classificacao_controle"] = base.motivo.map(
        {"maioria_f": "feminino", "maioria_m": "masculino", "sem_socio": "sem_socio"}
    ).fillna("misto_indeterminado")
    return base.reset_index()


def resumo(base, titulo):
    total = len(base)
    vc = base.motivo.value_counts()
    print(f"\n--- {titulo} ({total:,} empresas) ---")
    for k, rot in ROTULOS:
        print(f"  {rot:<50} {vc.get(k, 0):>7,}  {vc.get(k, 0) / total:6.1%}")
    f, m = vc.get("maioria_f", 0), vc.get("maioria_m", 0)
    com_socio = total - vc.get("sem_socio", 0)
    if f + m:
        print(f"  controle definido: {f + m:,} ({(f + m) / com_socio:.1%} das com sócio, "
              f"{(f + m) / total:.1%} do recorte); entre elas, {f / (f + m):.1%} femininas")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excluir-administradores", action="store_true")
    a = ap.parse_args()

    salt = os.getenv("ID_SALT")
    if not salt:
        sys.exit("ID_SALT vazio no .env (gere com: python -c \"import secrets; print(secrets.token_hex(16))\")")

    socios = ler("Socios_*.parquet").drop_duplicates()
    empresas = ler("Empresas_*.parquet")
    qual = ler("dominio_qualificacoes.parquet")
    nat = ler("dominio_naturezas.parquet")

    socios["tipo"] = socios.identificador_socio.map(TIPO).fillna("ES")
    desc = dict(zip(qual.codigo.str.zfill(2), qual.descricao.map(sem_acento)))
    socios["qual_desc"] = socios.qualificacao_socio.str.zfill(2).map(desc).fillna("")
    socios["excluido"] = socios.qual_desc.map(lambda d: bool(EXCLUIR.search(d)))
    socios["admin"] = socios.qual_desc.map(lambda d: bool(ADMIN.search(d)))

    # identificador derivado (RN-09): hash com sal da máscara do CPF e do nome completo normalizado
    socios["id_derivado"] = [
        hashlib.sha256(f"{salt}|{m}|{normalizar_nome(n)}".encode()).hexdigest()[:16]
        for m, n in zip(socios.cnpj_cpf_socio, socios.nome_socio)]
    dup = socios.duplicated(["cnpj_basico", "id_derivado", "qualificacao_socio"])
    print(f"vínculos repetidos (mesmo id, empresa e qualificação): {int(dup.sum()):,} (removidos)")
    socios = socios[~dup].copy()

    # RN-04: gênero pelo primeiro nome (todos os sócios pessoa física; o vínculo decide a elegibilidade)
    pf = socios.tipo.eq("PF")
    socios["primeiro_nome"] = ""
    socios.loc[pf, "primeiro_nome"] = socios.loc[pf, "nome_socio"].map(primeiro_nome)
    nomes = sorted(set(socios.loc[pf, "primeiro_nome"]) - {""})
    cache = carregar_cache()
    print(f"sócios PF: {int(pf.sum()):,} | primeiros nomes distintos: {len(nomes):,} | "
          f"fora do cache: {len(set(nomes) - set(cache)):,}")
    completar_cache(nomes, cache)
    cls = socios.loc[pf, "primeiro_nome"].map(lambda n: classificar(n, cache, LIMIAR_GENERO))
    socios["genero"] = "I"
    socios.loc[pf, "genero"] = cls.where(cls.isin(["F", "M"]), "I")
    socios["confianca"] = 0.0
    socios.loc[pf, "confianca"] = socios.loc[pf, "primeiro_nome"].map(lambda n: confianca(n, cache)).round(3)

    print(f"\n--- gênero dos sócios pessoa física (RN-04, limiar {LIMIAR_GENERO:.0%}) ---")
    for k, rot in (("F", "feminino"), ("M", "masculino"),
                   ("I_ambiguo", "indeterminado: ambíguo"), ("I_ausente", "indeterminado: nome ausente")):
        print(f"  {rot:<30} {int((cls == k).sum()):>8,}  {(cls == k).mean():6.1%}")

    # RN-03: quem conta como sócio
    print("\n--- qualificações dos sócios pessoa física (RN-03) ---")
    tab = (socios[pf].groupby(["qualificacao_socio", "qual_desc"])
           .agg(n=("cnpj_basico", "size"), excluido=("excluido", "max"), admin=("admin", "max"))
           .reset_index().sort_values("n", ascending=False).head(12))
    for r in tab.itertuples():
        marca = "excluída" if r.excluido else ("entra*" if r.admin else "entra")
        print(f"  {r.qualificacao_socio} {r.qual_desc[:38]:<38} {r.n:>7,}  {marca}")
    print("  * administrador: entra na regra padrão e sai com --excluir-administradores")

    el_padrao = pf & ~socios.excluido
    el_estrito = el_padrao & ~socios.admin
    base_a = classificar_empresas(empresas, socios, el_padrao)
    base_b = classificar_empresas(empresas, socios, el_estrito)
    resumo(base_a, "RN-03 padrão (administradores contam)")
    resumo(base_b, "RN-03 estrita (sem Diretor, Presidente e Conselheiro)")

    base = base_b if a.excluir_administradores else base_a
    socios["elegivel"] = el_estrito if a.excluir_administradores else el_padrao

    sem = base[base.motivo == "sem_socio"].merge(empresas[["cnpj_basico", "natureza_juridica"]], on="cnpj_basico")
    nat_desc = dict(zip(nat.codigo, nat.descricao))
    print("\nempresas sem sócio elegível, por natureza jurídica (top 5):")
    for cod, n_ in sem.natureza_juridica.value_counts().head(5).items():
        print(f"  {cod} {str(nat_desc.get(cod, '?'))[:50]:<50} {n_:>6,}")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    saida = socios[["cnpj_basico", "id_derivado", "tipo", "genero", "confianca", "qualificacao_socio",
                    "qual_desc", "data_entrada_sociedade", "faixa_etaria", "elegivel"]]
    assert "nome_socio" not in saida.columns and "cnpj_cpf_socio" not in saida.columns
    saida.to_parquet(PROCESSED / "socios_classificados.parquet", index=False)
    cols = ["cnpj_basico", "classificacao_controle", "motivo", "n_socios_total", "n_socios_elegiveis",
            "pct_indeterminados", "tem_socio_pj", "n_f", "n_m", "n_i"]
    base[cols].to_parquet(PROCESSED / "empresas_classificadas.parquet", index=False)
    regra = "estrita" if a.excluir_administradores else "padrão"
    print(f"\ngravado em {PROCESSED}: {len(saida):,} vínculos de sócios e {len(base):,} empresas (RN-03 {regra})")


if __name__ == "__main__":
    main()