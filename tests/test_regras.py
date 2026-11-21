"""Testes de dados: RN-01 a RN-05 e RN-09 sobre os arquivos gerados pelo pipeline.
Não tocam no banco nem na rede.

  data/interim/contratos_recorte.parquet
  data/processed/socios_classificados.parquet
  data/processed/empresas_classificadas.parquet

Uso, na raiz do repositório:  python -m pytest tests -v
"""
import importlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "etl"))

from config import DATA_FIM, DATA_INI, INTERIM, LIMIAR_GENERO, PROCESSED  # noqa: E402

m06 = importlib.import_module("06_classificar_empresas")

VALOR_MAX = 1_000_000_000           # RN-02
MAX_ORGAOS = 50
CLASSES = {"feminino", "masculino", "misto_indeterminado", "sem_socio"}   # CHECK do schema
PADRAO_CPF = r"\*{3}\d{3}\.?\d{3}\*{2}|\b\d{11}\b|\d{3}\.\d{3}\.\d{3}-\d{2}"


def ler(caminho):
    if not caminho.exists():
        pytest.skip(f"falta {caminho.name}: rode o pipeline antes")
    return pd.read_parquet(caminho)


def exemplos(df, colunas, n=5):
    return df[colunas].head(n).to_string(index=False)


@pytest.fixture(scope="module")
def contratos():
    return ler(INTERIM / "contratos_recorte.parquet")


@pytest.fixture(scope="module")
def socios():
    df = ler(PROCESSED / "socios_classificados.parquet")
    df["elegivel"] = df["elegivel"].fillna(False).astype(bool)
    return df


@pytest.fixture(scope="module")
def empresas():
    return ler(PROCESSED / "empresas_classificadas.parquet")


@pytest.fixture(scope="module")
def recalculo(socios, empresas):
    """Contagens por empresa recalculadas a partir dos vínculos (o 06 conta por vínculo)."""
    el = socios[socios["elegivel"]]
    cont = (el.groupby(["cnpj_basico", "genero"]).size().unstack(fill_value=0)
            .reindex(columns=["F", "M", "I"], fill_value=0))
    cont.columns = ["r_f", "r_m", "r_i"]
    pj = socios[socios["tipo"] == "PJ"].groupby("cnpj_basico").size().rename("r_pj")
    tot = socios.groupby("cnpj_basico").size().rename("r_total")
    e = empresas.set_index("cnpj_basico").join(cont).join(pj).join(tot)
    cols = ["r_f", "r_m", "r_i", "r_pj", "r_total"]
    e[cols] = e[cols].fillna(0).astype(int)
    e["r_n"] = e.r_f + e.r_m + e.r_i
    return e.reset_index()


# ---------------------------------------------------------------- RN-01
def test_rn01_raiz_do_contrato_tem_8_digitos(contratos):
    raiz = contratos["cnpj_raiz_fornecedor"].dropna().astype(str)
    ruins = raiz[~raiz.str.fullmatch(r"\d{8}")]
    assert ruins.empty, f"raízes fora do formato: {ruins.head().tolist()}"


def test_rn01_uma_linha_por_raiz_nas_empresas(empresas):
    assert empresas["cnpj_basico"].astype(str).str.fullmatch(r"\d{8}").all()
    assert empresas["cnpj_basico"].is_unique


def test_rn01_toda_raiz_do_recorte_tem_cadastro(contratos, empresas):
    raiz = contratos["cnpj_raiz_fornecedor"].dropna()
    sem = raiz[~raiz.isin(set(empresas["cnpj_basico"]))]
    parcela = len(sem) / max(len(raiz), 1)
    assert parcela <= 0.001, (f"{sem.nunique()} raízes sem cadastro em {len(sem)} contratos "
                              f"({parcela:.3%}), ex.: {sorted(sem.unique())[:5]}")


# ---------------------------------------------------------------- RN-02
def test_rn02_numero_de_controle_e_unico(contratos):
    assert contratos["numero_controle_pncp"].is_unique


def test_rn02_valor_global_positivo_e_ate_1_bi(contratos):
    v = pd.to_numeric(contratos["valor_global"], errors="coerce")
    assert v.notna().all(), "há valor_global nulo ou não numérico"
    assert (v > 0).all(), "há valor_global <= 0"
    assert (v <= VALOR_MAX).all(), f"{int((v > VALOR_MAX).sum())} contratos acima de R$ 1 bi"


def test_rn02_assinatura_dentro_do_periodo(contratos):
    d = pd.to_datetime(contratos["data_assinatura"], errors="coerce")
    assert d.notna().all(), "há data_assinatura nula"
    fora = contratos[(d < pd.Timestamp(DATA_INI)) | (d > pd.Timestamp(DATA_FIM))]
    assert fora.empty, f"{len(fora)} contratos assinados fora de {DATA_INI}..{DATA_FIM}"


def test_rn02_sem_contrato_de_receita(contratos):
    if "receita" not in contratos.columns:
        pytest.skip("a coluna 'receita' não está no recorte (já foi filtrada antes)")
    assert not contratos["receita"].fillna(False).astype(bool).any()


def test_recorte_tem_no_maximo_50_orgaos(contratos):
    assert contratos["orgao_cnpj"].nunique() <= MAX_ORGAOS


# ---------------------------------------------------------------- RN-03
def test_rn03_so_pessoa_fisica_e_elegivel(socios):
    ruim = socios[socios["elegivel"] & (socios["tipo"] != "PF")]
    assert ruim.empty, f"{len(ruim)} vínculos PJ/ES marcados como elegíveis"


def test_rn03_qualificacoes_excluidas_nao_sao_elegiveis(socios):
    exc = socios["qual_desc"].fillna("").map(lambda d: bool(m06.EXCLUIR.search(d)))
    ruim = socios[exc & socios["elegivel"]]
    assert ruim.empty, f"{len(ruim)} procuradores/representantes etc. elegíveis:\n" + \
        exemplos(ruim, ["cnpj_basico", "qual_desc"])


def test_rn03_ha_socios_elegiveis(socios):
    assert socios["elegivel"].any()


def test_rn03_contagens_da_empresa_conferem_com_os_vinculos(recalculo):
    pares = (("n_socios_total", "r_total"), ("n_socios_elegiveis", "r_n"),
             ("n_f", "r_f"), ("n_m", "r_m"), ("n_i", "r_i"))
    for guardada, calculada in pares:
        ruim = recalculo[recalculo[guardada].astype(int) != recalculo[calculada]]
        assert ruim.empty, f"{guardada}: {len(ruim)} empresas divergem:\n" + \
            exemplos(ruim, ["cnpj_basico", guardada, calculada])


def test_rn03_tem_socio_pj_confere(recalculo):
    ruim = recalculo[recalculo["tem_socio_pj"].astype(bool) != (recalculo["r_pj"] > 0)]
    assert ruim.empty, f"{len(ruim)} empresas com tem_socio_pj incoerente"


def test_rn03_vinculo_nao_se_repete(socios):
    chave = socios["qual_desc"].where(socios["qual_desc"].fillna("") != "", socios["qualificacao_socio"])
    dup = socios.assign(q=chave).duplicated(["cnpj_basico", "id_derivado", "q"])
    assert not dup.any(), f"{int(dup.sum())} vínculos repetidos (a chave da ponte no banco falharia)"


# ---------------------------------------------------------------- RN-04
def test_rn04_genero_so_f_m_ou_i(socios):
    assert socios["genero"].notna().all()
    assert set(socios["genero"].unique()) <= {"F", "M", "I"}


def test_rn04_tipo_so_pf_pj_ou_es(socios):
    assert set(socios["tipo"].dropna().unique()) <= {"PF", "PJ", "ES"}


def test_rn04_confianca_entre_0_e_1(socios):
    c = pd.to_numeric(socios["confianca"], errors="coerce")
    assert c.notna().all()
    assert ((c >= 0) & (c <= 1)).all()


def test_rn04_f_ou_m_exige_confianca_no_limiar(socios):
    definidos = socios[socios["genero"].isin(["F", "M"])]
    c = pd.to_numeric(definidos["confianca"])
    abaixo = definidos[c < LIMIAR_GENERO - 1e-9]
    assert abaixo.empty, f"{len(abaixo)} sócios com gênero definido e confiança < {LIMIAR_GENERO}"


def test_rn04_indeterminado_pf_fica_abaixo_do_limiar(socios):
    ind = socios[(socios["tipo"] == "PF") & (socios["genero"] == "I")]
    c = pd.to_numeric(ind["confianca"])
    acima = ind[c >= LIMIAR_GENERO + 5e-4]          # folga do arredondamento em 3 casas
    assert acima.empty, f"{len(acima)} PF indeterminados com confiança acima do limiar"


def test_rn04_nao_pf_nao_tem_genero(socios):
    nao_pf = socios[socios["tipo"] != "PF"]
    assert (nao_pf["genero"] == "I").all()
    assert (pd.to_numeric(nao_pf["confianca"]) == 0).all()


def test_rn04_mesmo_socio_tem_um_so_genero_e_tipo(socios):
    n = socios.groupby("id_derivado")[["tipo", "genero"]].nunique().max()
    assert n.max() <= 1, f"id_derivado com mais de um valor: {n.to_dict()} (a dim_socio pegaria um ao acaso)"


# ---------------------------------------------------------------- RN-05
def test_rn05_classes_compativeis_com_o_schema(empresas):
    achadas = set(empresas["classificacao_controle"].dropna().unique())
    assert achadas <= CLASSES, f"valores fora do CHECK do schema: {sorted(achadas - CLASSES)}"
    assert empresas["classificacao_controle"].notna().all()


def test_rn05_motivo_segue_a_ordem_de_decisao(recalculo):
    """PJ > sem sócio > mais de 1/3 indeterminados > maioria F > maioria M > sem maioria."""
    r = recalculo
    esperado = np.select(
        [(r.r_pj > 0).to_numpy(), (r.r_n == 0).to_numpy(), (3 * r.r_i > r.r_n).to_numpy(),
         (2 * r.r_f > r.r_n).to_numpy(), (2 * r.r_m > r.r_n).to_numpy()],
        ["socio_pj", "sem_socio", "indeterminados", "maioria_f", "maioria_m"], default="sem_maioria")
    ruim = r[esperado != r["motivo"].to_numpy()]
    assert ruim.empty, f"{len(ruim)} empresas com motivo diferente do esperado:\n" + \
        exemplos(ruim, ["cnpj_basico", "motivo", "r_f", "r_m", "r_i", "r_pj"])


def test_rn05_classe_decorre_do_motivo(empresas):
    mapa = {"maioria_f": "feminino", "maioria_m": "masculino", "sem_socio": "sem_socio"}
    esperada = empresas["motivo"].map(mapa).fillna("misto_indeterminado")
    ruim = empresas[esperada != empresas["classificacao_controle"]]
    assert ruim.empty, exemplos(ruim, ["cnpj_basico", "motivo", "classificacao_controle"])


def test_rn05_sem_socio_so_sem_elegivel_e_sem_pj(recalculo):
    sem = recalculo["classificacao_controle"] == "sem_socio"
    esperado = (recalculo["r_n"] == 0) & (recalculo["r_pj"] == 0)
    ruim = recalculo[sem != esperado]
    assert ruim.empty, exemplos(ruim, ["cnpj_basico", "classificacao_controle", "r_n", "r_pj"])


def test_rn05_pct_indeterminados_confere(recalculo):
    r = recalculo
    esperado = np.where(r.r_n > 0, (100 * r.r_i / r.r_n.where(r.r_n > 0, 1)).round(2), 0.0)
    dif = (pd.to_numeric(r["pct_indeterminados"]) - esperado).abs()
    assert (dif <= 0.01).all(), f"{int((dif > 0.01).sum())} empresas com pct_indeterminados incoerente"


# ---------------------------------------------------------------- RN-09 (minimização)
@pytest.mark.parametrize("arquivo", ["socios_classificados.parquet", "empresas_classificadas.parquet"])
def test_rn09_sem_coluna_de_nome_ou_cpf(arquivo):
    df = ler(PROCESSED / arquivo)
    proibidas = [c for c in df.columns if re.search(r"nome|cpf", c, re.IGNORECASE)]
    assert not proibidas, f"colunas proibidas em {arquivo}: {proibidas}"


@pytest.mark.parametrize("arquivo", ["socios_classificados.parquet", "empresas_classificadas.parquet"])
def test_rn09_nenhum_valor_parece_cpf(arquivo):
    df = ler(PROCESSED / arquivo)
    for col in df.select_dtypes(include=["object", "string"]).columns:
        achou = df[col].astype(str).str.contains(PADRAO_CPF, regex=True, na=False)
        assert not achou.any(), f"coluna {col} tem valores com formato de CPF"


def test_rn09_identificador_do_socio_e_hash_de_16_caracteres(socios):
    ids = socios["id_derivado"].astype(str)
    ruins = ids[~ids.str.fullmatch(r"[0-9a-f]{16}")]
    assert ruins.empty, f"{len(ruins)} identificadores fora do formato (16 hex)"