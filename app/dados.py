"""Camada de dados do painel.

Duas fontes com o MESMO formato de saída:
  ficticio()  dados sintéticos (não representam nada real)
  banco(url)  consulta o PostgreSQL do Aiven

Saída: (contratos, ponte)
  contratos  uma linha por contrato com fornecedor identificado (CNPJ válido)
  ponte      vínculos elegíveis cnpj_raiz x sk_socio (só para a concentração societária, RN-07)
"""
import numpy as np
import pandas as pd

CLASSES = ["feminino", "masculino", "misto_indeterminado", "sem_socio"]      # CHECK do schema
ROTULO = {"feminino": "Feminino", "masculino": "Masculino",
          "misto_indeterminado": "Misto/indeterminado", "sem_socio": "Sem sócio elegível"}
FAIXAS_VALOR = ["até R$ 100 mil", "R$ 100 mil a 1 mi", "R$ 1 a 10 mi", "R$ 10 a 100 mi",
                "acima de R$ 100 mi"]
FAIXAS_NEGRA = ["até 30%", "30% a 50%", "50% a 70%", "70% ou mais"]
SEM_DADO = "Sem dado"
COLUNAS = ["numero_controle", "orgao", "uf_orgao", "cnpj_raiz", "fornecedor", "porte",
           "uf_fornecedor", "municipio_fornecedor", "pct_negra", "classe", "valor", "data",
           "modalidade"]

SQL_CONTRATOS = """
SELECT c.numero_controle_pncp, o.razao_social, mo.uf,
       f.cnpj_raiz, f.razao_social, f.porte, f.uf, mf.nome, mf.pct_negra,
       f.classificacao_controle, c.valor_global, t.data, md.nome
FROM fato_contrato c
JOIN dim_orgao o        ON o.sk_orgao = c.sk_orgao
JOIN dim_fornecedor f   ON f.cnpj_raiz = c.cnpj_raiz_fornecedor      -- exclui PF e estrangeiro (raiz nula)
JOIN dim_tempo t        ON t.sk_tempo = c.sk_tempo
LEFT JOIN dim_modalidade md ON md.sk_modalidade = c.sk_modalidade
LEFT JOIN dim_municipio mo  ON mo.codigo_ibge = c.codigo_ibge        -- município do contrato (órgão)
LEFT JOIN dim_municipio mf  ON mf.codigo_ibge = f.codigo_ibge        -- município do fornecedor (proxy racial)
WHERE c.valor_global > 0
"""
SQL_PONTE = "SELECT cnpj_raiz, sk_socio FROM ponte_empresa_socio WHERE elegivel"


def preparar(df):
    """Tipos, rótulos e faixas usados pelo painel."""
    df = df.copy()
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=["valor"])
    df["pct_negra"] = pd.to_numeric(df["pct_negra"], errors="coerce")
    df["data"] = pd.to_datetime(df["data"])
    df["mes"] = df["data"].dt.month
    df["classe_rotulo"] = df["classe"].map(ROTULO)
    df["faixa_valor"] = pd.cut(df["valor"], [0, 1e5, 1e6, 1e7, 1e8, np.inf], labels=FAIXAS_VALOR)
    faixa = pd.cut(df["pct_negra"], [-0.01, 30, 50, 70, 100.01], labels=FAIXAS_NEGRA, right=False)
    df["faixa_negra"] = faixa.astype(object).where(faixa.notna(), SEM_DADO)
    for c in ("orgao", "fornecedor", "modalidade"):
        df[c] = df[c].fillna("não informado")
    df["porte"] = df["porte"].fillna("Não informado")
    for c in ("uf_orgao", "uf_fornecedor", "municipio_fornecedor"):
        df[c] = df[c].fillna("—")
    return df.reset_index(drop=True)


def banco(url):
    import psycopg2
    con = psycopg2.connect(url, connect_timeout=30)
    try:
        cur = con.cursor()
        cur.execute(SQL_CONTRATOS)
        contratos = pd.DataFrame(cur.fetchall(), columns=COLUNAS)
        cur.execute(SQL_PONTE)
        ponte = pd.DataFrame(cur.fetchall(), columns=["cnpj_raiz", "sk_socio"])
    finally:
        con.close()
    return preparar(contratos), ponte


# UF: (peso na amostra, % de pretos e pardos de referência para o sorteio)
UF = {"AC": (0.4, 75), "AL": (0.8, 78), "AP": (0.4, 80), "AM": (1.5, 80), "BA": (6, 80),
      "CE": (4, 72), "DF": (4, 58), "ES": (2.5, 62), "GO": (4, 60), "MA": (2, 82),
      "MT": (2.5, 65), "MS": (2, 55), "MG": (10, 58), "PA": (3, 82), "PB": (1.5, 70),
      "PR": (6, 30), "PE": (4, 70), "PI": (1, 80), "RJ": (7, 55), "RN": (1.5, 65),
      "RS": (6, 20), "RO": (1, 70), "RR": (0.3, 80), "SC": (4, 18), "SP": (18, 38),
      "SE": (1, 75), "TO": (0.8, 78)}


def ficticio(semente=7, n_forn=4000, n_contr=30000, n_orgaos=50, n_socios=6000):
    """Dados sintéticos com o formato do banco. Nada aqui é real."""
    rng = np.random.default_rng(semente)
    siglas = list(UF)
    peso = np.array([UF[u][0] for u in siglas], dtype=float)
    peso /= peso.sum()

    muni = [(u, f"Município fictício {u}-{i}", float(np.clip(rng.normal(UF[u][1], 10), 2, 98)))
            for u in siglas for i in range(1, 7)]
    muni = pd.DataFrame(muni, columns=["uf", "nome", "pct_negra"])
    por_uf = {u: g.reset_index(drop=True) for u, g in muni.groupby("uf")}

    raizes = rng.choice(90_000_000, n_forn, replace=False) + 10_000_000
    forn = pd.DataFrame({"cnpj_raiz": raizes.astype(str),
                         "fornecedor": [f"EMPRESA FICTÍCIA {i:05d} LTDA" for i in range(n_forn)]})
    forn["porte"] = rng.choice(["Microempresa", "Empresa de pequeno porte", "Demais", "Não informado"],
                               n_forn, p=[.40, .25, .30, .05])
    forn["uf_fornecedor"] = rng.choice(siglas, n_forn, p=peso)
    forn["classe"] = rng.choice(CLASSES, n_forn, p=[.205, .434, .246, .115])
    escolhidos = [por_uf[u].iloc[int(rng.integers(0, 6))] for u in forn["uf_fornecedor"]]
    forn["municipio_fornecedor"] = [m["nome"] for m in escolhidos]
    forn["pct_negra"] = [m["pct_negra"] for m in escolhidos]
    sem_traducao = rng.random(n_forn) < 0.003                      # imita os pares sem código IBGE
    forn.loc[sem_traducao, "pct_negra"] = np.nan
    forn.loc[sem_traducao, "municipio_fornecedor"] = None

    orgs = pd.DataFrame({"orgao": [f"Órgão fictício {i:02d}" for i in range(1, n_orgaos + 1)],
                         "uf_orgao": rng.choice(siglas, n_orgaos, p=peso)})
    w_org = 1 / np.arange(1, n_orgaos + 1) ** 0.8
    w_org /= w_org.sum()
    w_forn = 1 / np.arange(1, n_forn + 1) ** 0.6
    rng.shuffle(w_forn)
    w_forn /= w_forn.sum()

    c = forn.iloc[rng.choice(n_forn, n_contr, p=w_forn)].reset_index(drop=True)
    i_org = rng.choice(n_orgaos, n_contr, p=w_org)
    c["numero_controle"] = [f"FICT-{i:07d}" for i in range(n_contr)]
    c["orgao"] = orgs["orgao"].to_numpy()[i_org]
    c["uf_orgao"] = orgs["uf_orgao"].to_numpy()[i_org]
    ajuste = c["classe"].map({"feminino": -0.25, "masculino": 0.0,
                              "misto_indeterminado": 0.1, "sem_socio": -0.1}).to_numpy()
    valor = np.exp(rng.normal(11.0 + ajuste, 1.7))
    valor = np.where(rng.random(n_contr) < 0.003, valor * 40, valor)    # cauda pesada
    c["valor"] = np.clip(valor, 1_000, 1_000_000_000).round(2)
    c["data"] = pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 365, n_contr), unit="D")
    c["modalidade"] = rng.choice(["Contrato | Compras", "Contrato | Serviços", "Contrato | Obras",
                                  "Empenho | Compras"], n_contr, p=[.35, .40, .10, .15])

    w_soc = 1 / np.arange(1, n_socios + 1) ** 0.7
    rng.shuffle(w_soc)
    w_soc /= w_soc.sum()
    vinculos = []
    for raiz, classe in zip(forn["cnpj_raiz"], forn["classe"]):
        if classe == "sem_socio":
            continue
        k = int(rng.choice([1, 2, 3, 4], p=[.45, .30, .15, .10]))
        for s in rng.choice(n_socios, k, replace=False, p=w_soc):
            vinculos.append((raiz, int(s)))
    ponte = pd.DataFrame(vinculos, columns=["cnpj_raiz", "sk_socio"]).drop_duplicates()
    return preparar(c[COLUNAS]), ponte


def carregar(fonte, url=None):
    if fonte == "banco":
        if not url:
            raise ValueError("DATABASE_URL ausente")
        return banco(url)
    return ficticio()