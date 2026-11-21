"""Fase 2: carrega o modelo estrela no PostgreSQL do Aiven (só o recorte).

Entradas (locais, em data/): contratos_recorte.parquet (03), receita_filtrada (05),
socios_classificados e empresas_classificadas (06), municipios_cor_raca e
municipios_receita_ibge (08).
Nenhum nome de sócio e nenhum CPF chega ao banco (RN-09).

Uso:
  python 07_carregar_aiven.py --simular      # prepara tudo e confere, sem tocar no banco
  python 07_carregar_aiven.py                # carrega (recusa se o banco já tiver dados)
  python 07_carregar_aiven.py --recarregar   # esvazia as tabelas e carrega de novo
"""
import argparse
import csv
import io
import sys
from datetime import timedelta

import duckdb
import psycopg2

from config import DATA_FIM, DATA_INI, DATABASE_URL, INTERIM, PROCESSED, ROOT

RF = INTERIM / "receita_filtrada"
RECORTE = INTERIM / "contratos_recorte.parquet"
SOC = PROCESSED / "socios_classificados.parquet"
EMP = PROCESSED / "empresas_classificadas.parquet"
MUN = PROCESSED / "municipios_cor_raca.parquet"
TRAD = PROCESSED / "municipios_receita_ibge.parquet"
INDICES = ROOT / "etl" / "sql" / "indices.sql"
NULO = "\\N"
LIMITE_MB = 600
TABELAS = ["fato_contrato", "ponte_empresa_socio", "dim_socio", "dim_fornecedor",
           "dim_modalidade", "dim_cnae", "dim_municipio", "dim_orgao", "dim_tempo"]


def preparar(con):
    rec, socp, empp, rf, mun, trad = (RECORTE.as_posix(), SOC.as_posix(), EMP.as_posix(),
                                      RF.as_posix(), MUN.as_posix(), TRAD.as_posix())
    d = {}

    tempo, dia = [], DATA_INI
    while dia <= DATA_FIM:
        tempo.append((dia.strftime("%Y%m%d"), dia.isoformat(), dia.year, dia.month, (dia.month - 1) // 3 + 1))
        dia += timedelta(days=1)
    d["dim_tempo"] = tempo

    d["dim_orgao"] = con.execute(f"""
        SELECT lpad(orgao_cnpj, 14, '0'), any_value(orgao_razao_social),
               any_value(esfera_id), any_value(poder_id)
        FROM '{rec}' WHERE orgao_cnpj IS NOT NULL GROUP BY 1""").fetchall()

    # todos os municípios do Censo 2022 (com proxy racial) + municípios do PNCP que faltarem
    d["dim_municipio"] = con.execute(f"""
        SELECT codigo_ibge, nome, uf, CAST(populacao AS VARCHAR),
               CAST(pct_negra AS VARCHAR), CAST(pct_branca AS VARCHAR)
        FROM '{mun}'
        UNION ALL
        SELECT left(codigo_ibge, 7), any_value(municipio_nome), any_value(uf_sigla),
               CAST(NULL AS VARCHAR), CAST(NULL AS VARCHAR), CAST(NULL AS VARCHAR)
        FROM '{rec}'
        WHERE codigo_ibge IS NOT NULL
          AND left(codigo_ibge, 7) NOT IN (SELECT codigo_ibge FROM '{mun}')
        GROUP BY 1""").fetchall()

    d["dim_cnae"] = con.execute(f"""
        SELECT lpad(codigo, 7, '0'), any_value(descricao)
        FROM read_parquet('{rf}/dominio_cnaes.parquet') GROUP BY 1""").fetchall()

    d["dim_modalidade"] = con.execute(f"""
        SELECT coalesce(tipo_contrato_id, 0) * 100 + coalesce(categoria_processo_id, 0) AS id,
               any_value(coalesce(tipo_contrato_nome, 'não informado') || ' | ' ||
                         coalesce(categoria_processo_nome, 'não informado'))
        FROM '{rec}' GROUP BY 1""").fetchall()

    d["dim_fornecedor"] = con.execute(f"""
        WITH est AS (
            SELECT cnpj_basico, cnae_principal, uf, municipio
            FROM read_parquet('{rf}/Estabelecimentos_*.parquet')
            QUALIFY row_number() OVER (PARTITION BY cnpj_basico
                                       ORDER BY identificador_matriz_filial, cnpj_ordem) = 1),
        emp AS (
            SELECT * FROM read_parquet('{rf}/Empresas_*.parquet')
            QUALIFY row_number() OVER (PARTITION BY cnpj_basico ORDER BY razao_social) = 1),
        nat AS (SELECT codigo, descricao FROM read_parquet('{rf}/dominio_naturezas.parquet')),
        trad AS (SELECT cod_receita, uf, any_value(codigo_ibge) AS codigo_ibge
                 FROM read_parquet('{trad}') GROUP BY 1, 2)
        SELECT emp.cnpj_basico,
               CASE WHEN emp.natureza_juridica = '2135' THEN 'EMPRESARIO INDIVIDUAL (NOME OMITIDO)'
                    ELSE emp.razao_social END,
               CASE emp.porte WHEN '01' THEN 'Microempresa' WHEN '03' THEN 'Empresa de pequeno porte'
                              WHEN '05' THEN 'Demais' ELSE 'Não informado' END,
               emp.natureza_juridica || ' - ' || coalesce(nat.descricao, ''),
               lpad(est.cnae_principal, 7, '0'),
               trad.codigo_ibge,
               est.uf,
               cls.classificacao_controle,
               CAST(cls.n_socios_elegiveis AS VARCHAR),
               CAST(cls.pct_indeterminados AS VARCHAR)
        FROM emp
        JOIN read_parquet('{empp}') AS cls ON cls.cnpj_basico = emp.cnpj_basico
        LEFT JOIN est ON est.cnpj_basico = emp.cnpj_basico
        LEFT JOIN nat ON nat.codigo = emp.natureza_juridica
        LEFT JOIN trad ON trad.cod_receita = est.municipio AND trad.uf = est.uf""").fetchall()

    d["dim_socio"] = con.execute(f"""
        SELECT id_derivado, any_value(tipo), any_value(genero),
               CAST(round(any_value(confianca), 3) AS VARCHAR),
               CAST(TRY_CAST(any_value(faixa_etaria) AS INTEGER) AS VARCHAR)
        FROM read_parquet('{socp}') GROUP BY id_derivado""").fetchall()

    d["ponte"] = con.execute(f"""
        SELECT cnpj_basico, id_derivado,
               coalesce(nullif(qual_desc, ''), qualificacao_socio),
               CAST(TRY_CAST(substr(data_entrada_sociedade, 1, 4) || '-' ||
                             substr(data_entrada_sociedade, 5, 2) || '-' ||
                             substr(data_entrada_sociedade, 7, 2) AS DATE) AS VARCHAR),
               CAST(elegivel AS VARCHAR)
        FROM read_parquet('{socp}')""").fetchall()

    d["fato"] = con.execute(f"""
        SELECT numero_controle_pncp, lpad(orgao_cnpj, 14, '0'), cnpj_raiz_fornecedor,
               strftime(data_assinatura, '%Y%m%d'),
               coalesce(tipo_contrato_id, 0) * 100 + coalesce(categoria_processo_id, 0),
               left(codigo_ibge, 7),
               CAST(valor_global AS VARCHAR), CAST(valor_parcela AS VARCHAR),
               CAST(CASE WHEN data_vigencia_fim >= data_vigencia_inicio
                         THEN date_diff('day', data_vigencia_inicio, data_vigencia_fim) END AS VARCHAR),
               left(objeto_contrato, 500)
        FROM '{rec}'
        WHERE data_assinatura BETWEEN DATE '{DATA_INI}' AND DATE '{DATA_FIM}'""").fetchall()
    return d


def verificar(d):
    forn = {r[0] for r in d["dim_fornecedor"]}
    municipios = {r[0] for r in d["dim_municipio"]}
    print("linhas preparadas:")
    for k, v in d.items():
        print(f"  {k:<16} {len(v):>9,}")
    sem_raiz = sum(1 for r in d["fato"] if not r[2])
    raiz_sem_cadastro = sum(1 for r in d["fato"] if r[2] and r[2] not in forn)
    ponte_fora = sum(1 for r in d["ponte"] if r[0] not in forn)
    chaves = [(r[0], r[1], r[2]) for r in d["ponte"]]
    dup_ponte = len(chaves) - len(set(chaves))
    dup_fato = len(d["fato"]) - len({r[0] for r in d["fato"]})
    dup_forn = len(d["dim_fornecedor"]) - len(forn)
    sem_ibge = sum(1 for r in d["dim_fornecedor"] if not r[5])
    fato_sem_mun = sum(1 for r in d["fato"] if r[5] and r[5] not in municipios)
    print(f"\ncontratos com fornecedor PF, estrangeiro ou sem CNPJ válido (raiz nula): {sem_raiz:,}")
    print(f"contratos com raiz de CNPJ sem cadastro na Receita filtrada: {raiz_sem_cadastro:,}")
    print(f"vínculos de sócios fora de dim_fornecedor: {ponte_fora:,}")
    print(f"fornecedores sem código IBGE de município: {sem_ibge:,} de {len(d['dim_fornecedor']):,}")
    print(f"contratos com município fora de dim_municipio: {fato_sem_mun:,}")
    print(f"chaves repetidas: ponte {dup_ponte:,} | fato {dup_fato:,} | fornecedor {dup_forn:,}")
    if ponte_fora or dup_ponte or dup_fato or dup_forn:
        sys.exit("corrija os itens acima antes de carregar")


def copiar(cur, tabela, colunas, linhas):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for r in linhas:
        w.writerow([NULO if v is None else v for v in r])
    buf.seek(0)
    cur.copy_expert(f"COPY {tabela} ({', '.join(colunas)}) FROM STDIN WITH (FORMAT csv, NULL '{NULO}')", buf)
    print(f"  {tabela:<22} {len(linhas):>9,} linhas")


def relatorio(cur):
    cur.execute("""SELECT relname, pg_total_relation_size(relid)
                   FROM pg_catalog.pg_statio_user_tables ORDER BY 2 DESC""")
    print("\ntamanho por tabela (dados e índices):")
    for nome, b in cur.fetchall():
        print(f"  {nome:<22} {b / 1e6:8.1f} MB")
    cur.execute("SELECT pg_database_size(current_database())")
    mb = cur.fetchone()[0] / 1e6
    print(f"  {'banco inteiro':<22} {mb:8.1f} MB (orçamento {LIMITE_MB} MB; limite do plano free: 1 GB)")
    if mb > LIMITE_MB:
        print("  ATENÇÃO: acima do orçamento. Reduza o recorte (N de órgãos) ou o texto do objeto.")


def carregar(d, recarregar):
    if not DATABASE_URL:
        sys.exit("DATABASE_URL vazio: confira o .env")
    con = psycopg2.connect(DATABASE_URL, connect_timeout=30)
    try:
        cur = con.cursor()
        cur.execute("ALTER TABLE ponte_empresa_socio ADD COLUMN IF NOT EXISTS "
                    "elegivel boolean NOT NULL DEFAULT true")
        cheias = []
        for t in TABELAS:
            cur.execute(f"SELECT count(*) FROM {t}")
            if cur.fetchone()[0]:
                cheias.append(t)
        if cheias and not recarregar:
            con.rollback()
            sys.exit(f"o banco já tem dados em: {', '.join(cheias)}. Use --recarregar para refazer.")
        if cheias:
            cur.execute("TRUNCATE " + ", ".join(TABELAS) + " RESTART IDENTITY CASCADE")
            print("tabelas esvaziadas")

        print("carregando:")
        copiar(cur, "dim_tempo", ["sk_tempo", "data", "ano", "mes", "trimestre"], d["dim_tempo"])
        copiar(cur, "dim_orgao", ["orgao_cnpj", "razao_social", "esfera_id", "poder_id"], d["dim_orgao"])
        copiar(cur, "dim_municipio",
               ["codigo_ibge", "nome", "uf", "populacao", "pct_negra", "pct_branca"], d["dim_municipio"])
        copiar(cur, "dim_cnae", ["cnae", "descricao"], d["dim_cnae"])
        copiar(cur, "dim_modalidade", ["id_origem", "nome"], d["dim_modalidade"])
        copiar(cur, "dim_fornecedor",
               ["cnpj_raiz", "razao_social", "porte", "natureza_juridica", "cnae_principal",
                "codigo_ibge", "uf", "classificacao_controle", "n_socios_elegiveis",
                "pct_indeterminados"], d["dim_fornecedor"])
        copiar(cur, "dim_socio", ["id_derivado", "tipo", "genero", "confianca", "faixa_etaria"],
               d["dim_socio"])

        cur.execute("SELECT id_derivado, sk_socio FROM dim_socio")
        sk_socio = dict(cur.fetchall())
        cur.execute("SELECT orgao_cnpj, sk_orgao FROM dim_orgao")
        sk_orgao = {k.strip(): v for k, v in cur.fetchall()}
        cur.execute("SELECT id_origem, sk_modalidade FROM dim_modalidade")
        sk_mod = dict(cur.fetchall())
        forn = {r[0] for r in d["dim_fornecedor"]}

        ponte = [(c, sk_socio[i], q, dt, el) for c, i, q, dt, el in d["ponte"]]
        copiar(cur, "ponte_empresa_socio",
               ["cnpj_raiz", "sk_socio", "qualificacao", "data_entrada", "elegivel"], ponte)

        fato = [(num, sk_orgao[org], raiz if raiz in forn else None, tempo, sk_mod[int(mod)],
                 ibge, vg, vp, prazo, obj)
                for num, org, raiz, tempo, mod, ibge, vg, vp, prazo, obj in d["fato"]]
        copiar(cur, "fato_contrato",
               ["numero_controle_pncp", "sk_orgao", "cnpj_raiz_fornecedor", "sk_tempo", "sk_modalidade",
                "codigo_ibge", "valor_global", "valor_parcela", "prazo_dias", "objeto_contrato"], fato)

        print("criando índices (depois da carga)")
        cur.execute(INDICES.read_text(encoding="utf-8"))
        con.commit()

        con.autocommit = True
        cur = con.cursor()
        cur.execute("ANALYZE")
        relatorio(cur)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--recarregar", action="store_true")
    a = ap.parse_args()

    for p in (RECORTE, SOC, EMP, MUN, TRAD):
        if not p.exists():
            sys.exit(f"não achei {p}: rode antes os scripts 03, 05, 06 e 08")
    for padrao in ("Empresas_*.parquet", "Estabelecimentos_*.parquet",
                   "dominio_cnaes.parquet", "dominio_naturezas.parquet"):
        if not list(RF.glob(padrao)):
            sys.exit(f"não achei {padrao} em {RF}: rode antes o 05_filtrar_receita.py")

    d = preparar(duckdb.connect())
    verificar(d)
    if a.simular:
        print("\nsimulação concluída: nada foi gravado no banco")
        return
    carregar(d, a.recarregar)


if __name__ == "__main__":
    main()