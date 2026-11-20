"""NDJSON bruto do PNCP -> Parquet tipado e deduplicado.

Schema declarado de propósito: a inferência automática quebra quando um arquivo
traz um campo sempre nulo. Regras aplicadas: RN-01 (CNPJ como texto, raiz de 8),
deduplicação por numeroControlePNCP, TRY_CAST em valores e datas, nomes sem
espaço duplo.

Uso:
  python 02_tratar_contratos.py --chaves   # confere os campos do JSON real e sai
  python 02_tratar_contratos.py            # trata e imprime o resumo
"""
import json
import sys

import duckdb

from config import INTERIM, RAW_PNCP

arquivos = sorted(RAW_PNCP.glob("*.ndjson"))     # .tmp (dia em escrita) fica de fora
if not arquivos:
    sys.exit(f"nenhum .ndjson em {RAW_PNCP}")

if "--chaves" in sys.argv:
    for a in arquivos:
        if a.stat().st_size > 0:
            with a.open(encoding="utf-8") as f:
                r = json.loads(f.readline())
            print(f"arquivo: {a.name}")
            for k, v in r.items():
                print(f"  {k}: {type(v).__name__}")
            sys.exit()
    sys.exit("todos os arquivos estão vazios")

COLUNAS = {
    "numeroControlePNCP": "VARCHAR",
    "numeroControlePncpCompra": "VARCHAR",
    "niFornecedor": "VARCHAR",
    "tipoPessoa": "VARCHAR",
    "nomeRazaoSocialFornecedor": "VARCHAR",
    "objetoContrato": "VARCHAR",
    "receita": "BOOLEAN",
    "valorGlobal": "DOUBLE",
    "valorInicial": "DOUBLE",
    "valorParcela": "DOUBLE",
    "valorAcumulado": "DOUBLE",
    "dataAssinatura": "VARCHAR",
    "dataVigenciaInicio": "VARCHAR",
    "dataVigenciaFim": "VARCHAR",
    "dataPublicacaoPncp": "VARCHAR",
    "dataAtualizacao": "VARCHAR",
    "dataAtualizacaoGlobal": "VARCHAR",
    "orgaoEntidade": "STRUCT(cnpj VARCHAR, razaoSocial VARCHAR, poderId VARCHAR, esferaId VARCHAR)",
    "unidadeOrgao": "STRUCT(ufSigla VARCHAR, municipioNome VARCHAR, codigoIbge VARCHAR, nomeUnidade VARCHAR)",
    "tipoContrato": "STRUCT(id INTEGER, nome VARCHAR)",
    "categoriaProcesso": "STRUCT(id INTEGER, nome VARCHAR)",
}
cols_sql = ", ".join(f"'{k}': '{v}'" for k, v in COLUNAS.items())
glob = f"{RAW_PNCP.as_posix()}/*.ndjson"
SRC = f"read_json('{glob}', format='newline_delimited', columns={{{cols_sql}}})"

DESTINO = INTERIM / "contratos.parquet"
P = DESTINO.as_posix()
tmp = INTERIM / "duckdb_tmp"
tmp.mkdir(exist_ok=True)

con = duckdb.connect()
con.execute("SET memory_limit='3GB'")             # baixe para 2GB se o PC tiver pouca RAM
con.execute(f"SET temp_directory='{tmp.as_posix()}'")

con.execute(rf"""
COPY (
  WITH dedup AS (
    SELECT * FROM {SRC}
    WHERE numeroControlePNCP IS NOT NULL
    QUALIFY row_number() OVER (PARTITION BY numeroControlePNCP
                               ORDER BY dataAtualizacaoGlobal DESC) = 1
  ),
  base AS (
    SELECT *, regexp_replace(coalesce(niFornecedor, ''), '\D', '', 'g') AS ni_digitos
    FROM dedup
  )
  SELECT
    numeroControlePNCP                                AS numero_controle_pncp,
    numeroControlePncpCompra                          AS numero_controle_pncp_compra,
    NULLIF(trim(niFornecedor), '')                    AS ni_fornecedor,
    upper(trim(tipoPessoa))                           AS tipo_pessoa,
    CASE WHEN upper(trim(tipoPessoa)) = 'PJ' AND length(ni_digitos) = 14
         THEN left(ni_digitos, 8) END                 AS cnpj_raiz_fornecedor,   -- RN-01
    regexp_replace(trim(nomeRazaoSocialFornecedor), '\s+', ' ', 'g') AS nome_fornecedor,
    TRY_CAST(valorGlobal    AS DECIMAL(18,2))         AS valor_global,
    TRY_CAST(valorInicial   AS DECIMAL(18,2))         AS valor_inicial,
    TRY_CAST(valorParcela   AS DECIMAL(18,2))         AS valor_parcela,
    TRY_CAST(valorAcumulado AS DECIMAL(18,2))         AS valor_acumulado,
    coalesce(receita, false)                          AS receita,
    TRY_CAST(dataAssinatura     AS DATE)              AS data_assinatura,
    TRY_CAST(dataVigenciaInicio AS DATE)              AS data_vigencia_inicio,
    TRY_CAST(dataVigenciaFim    AS DATE)              AS data_vigencia_fim,
    TRY_CAST(dataPublicacaoPncp AS TIMESTAMP)         AS data_publicacao,
    TRY_CAST(dataAtualizacaoGlobal AS TIMESTAMP)      AS data_atualizacao_global,
    orgaoEntidade.cnpj                                AS orgao_cnpj,
    orgaoEntidade.razaoSocial                         AS orgao_razao_social,
    orgaoEntidade.esferaId                            AS esfera_id,
    orgaoEntidade.poderId                             AS poder_id,
    upper(unidadeOrgao.ufSigla)                       AS uf_sigla,
    unidadeOrgao.municipioNome                        AS municipio_nome,
    unidadeOrgao.codigoIbge                           AS codigo_ibge,
    tipoContrato.id                                   AS tipo_contrato_id,
    tipoContrato.nome                                 AS tipo_contrato_nome,
    categoriaProcesso.id                              AS categoria_processo_id,
    categoriaProcesso.nome                            AS categoria_processo_nome,
    regexp_replace(trim(objetoContrato), '\s+', ' ', 'g') AS objeto_contrato
  FROM base
) TO '{P}' (FORMAT PARQUET);
""")


def q(sql):
    return con.execute(sql).fetchone()[0]


def contar(onde="true"):
    return q(f"SELECT count(*) FROM '{P}' WHERE {onde}")


bruto = q(f"SELECT count(*) FROM {SRC}")
n = contar()
distintas = q(f"SELECT count(DISTINCT cnpj_raiz_fornecedor) FROM '{P}'")
fora = contar("data_assinatura < DATE '2025-01-01' OR data_assinatura > DATE '2025-12-31'")
datas = con.execute(f"SELECT min(data_assinatura), max(data_assinatura) FROM '{P}'").fetchone()

print(f"arquivos .ndjson lidos   : {len(arquivos)}")
print(f"registros brutos         : {bruto:,}")
print(f"após deduplicação        : {n:,}  (removidos {bruto - n:,}, contando linhas sem chave)")
print("--- tipo de fornecedor ---")
for tp, c in con.execute(f"SELECT tipo_pessoa, count(*) FROM '{P}' GROUP BY 1 ORDER BY 2 DESC").fetchall():
    print(f"  {tp}: {c:,}")
print(f"PJ com raiz de 8 dígitos : {contar('cnpj_raiz_fornecedor IS NOT NULL'):,}")
print(f"raízes de CNPJ distintas : {distintas:,}")
print(f"valor_global nulo        : {contar('valor_global IS NULL'):,}")
print(f"valor_global <= 0        : {contar('valor_global <= 0'):,}")
print(f"valor_global > R$ 1 bi   : {contar('valor_global > 1000000000'):,}")
print(f"data_assinatura nula     : {contar('data_assinatura IS NULL'):,}")
print(f"data_assinatura mín/máx  : {datas[0]} a {datas[1]}")
print(f"assinados fora de 2025   : {fora:,}")
print("--- campo receita (contratos e soma de valor_global) ---")
for rec, c, s in con.execute(
        f"SELECT receita, count(*), sum(valor_global) FROM '{P}' GROUP BY 1 ORDER BY 1").fetchall():
    print(f"  receita={rec}: {c:,} contratos, R$ {s or 0:,.2f}")