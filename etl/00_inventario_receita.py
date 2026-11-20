"""T2/S1: inventário da Receita sem baixar os ZIPs inteiros.
1) tamanho real de todos os arquivos, via cabeçalho HTTP (V de Volume)
2) lê só o começo de Socios0 e Estabelecimentos0 (V de Veracidade)"""
import itertools
import sys

import pandas as pd
import requests

from config import INTERIM, RECEITA_URL, url_receita
from receita_stream import COLUNAS, registros_zip

if not RECEITA_URL:
    sys.exit("RECEITA_URL vazio: confira o .env na raiz do projeto")

N = 200_000
GRUPOS = {
    "Empresas": [f"Empresas{i}.zip" for i in range(10)],
    "Estabelecimentos": [f"Estabelecimentos{i}.zip" for i in range(10)],
    "Socios": [f"Socios{i}.zip" for i in range(10)],
    "Simples": ["Simples.zip"],
    "Dominio": ["Cnaes.zip", "Motivos.zip", "Municipios.zip", "Naturezas.zip",
                "Paises.zip", "Qualificacoes.zip"],
}


def tamanho(url):
    r = requests.head(url, allow_redirects=True, timeout=60)
    if r.status_code >= 400:          # alguns servidores não aceitam HEAD
        r = requests.get(url, stream=True, timeout=60)
        r.close()
    r.raise_for_status()
    return int(r.headers.get("Content-Length", 0))


def tamanhos():
    linhas = []
    for grupo, arqs in GRUPOS.items():
        for a in arqs:
            try:
                b = tamanho(url_receita(a))
            except requests.RequestException as e:
                print(f"AUSENTE/ERRO {a}: {e}")
                b = 0
            linhas.append({"grupo": grupo, "arquivo": a, "bytes": b})
    df = pd.DataFrame(linhas)
    df.to_csv(INTERIM / "inventario_tamanhos.csv", index=False)
    print((df.groupby("grupo").bytes.sum() / 1e9).round(2).to_string())
    print("total compactado (GB):", round(df.bytes.sum() / 1e9, 2))


def amostra(grupo, arquivo):
    cols = COLUNAS[grupo]
    rows = list(itertools.islice(registros_zip(url_receita(arquivo), len(cols)), N))
    df = pd.DataFrame(rows, columns=cols).replace("", pd.NA)
    nulos = (df.isna().mean() * 100).round(2)
    nulos.to_csv(INTERIM / f"inventario_nulos_{grupo}.csv", header=["pct_nulo"])
    print(f"\n== {grupo}: {len(df):,} linhas de {arquivo} (amostra sequencial, não aleatória) ==")
    print("colunas com nulos (%):\n", nulos[nulos > 0].to_string())
    print("linhas duplicadas:", int(df.duplicated().sum()))
    return df


if __name__ == "__main__":
    tamanhos()

    s = amostra("Socios", "Socios0.zip")
    print("tipo de sócio (1=PJ, 2=PF, 3=estrangeiro) %:\n",
          (s.identificador_socio.value_counts(normalize=True) * 100).round(2).to_string())
    pf = s[s.identificador_socio == "2"]
    print("máscaras de CPF distintas:", pf.cnpj_cpf_socio.nunique(),
          "| pares máscara+nome:", pf[["cnpj_cpf_socio", "nome_socio"]].drop_duplicates().shape[0])
    # trecho real para o documento de tipos de dado, com o nome já mascarado
    print(s.assign(nome_socio=s.nome_socio.str[:1] + "***").head(5).to_string())

    e = amostra("Estabelecimentos", "Estabelecimentos0.zip")
    print("matriz(1)/filial(2) %:\n",
          (e.identificador_matriz_filial.value_counts(normalize=True) * 100).round(2).to_string())
    print("situação cadastral %:\n",
          (e.situacao_cadastral.value_counts(normalize=True) * 100).round(2).to_string())
    print("tamanho do CNAE:", e.cnae_principal.str.len().value_counts().to_dict(),
          "| tamanho do município:", e.municipio.str.len().value_counts().to_dict())