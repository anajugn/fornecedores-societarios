"""Testes da camada de dados do painel (dados fictícios; sem rede e sem banco)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import dados  # noqa: E402


@pytest.fixture(scope="module")
def fic():
    return dados.ficticio(n_forn=500, n_contr=3000, n_socios=800)


def test_tem_as_colunas_que_o_painel_usa(fic):
    assert set(dados.COLUNAS) <= set(fic[0].columns)


def test_classes_compativeis_com_o_schema(fic):
    assert set(fic[0]["classe"]) <= set(dados.CLASSES)


def test_valores_respeitam_a_rn02(fic):
    v = fic[0]["valor"]
    assert (v > 0).all() and (v <= 1_000_000_000).all()


def test_numero_de_controle_e_unico(fic):
    assert fic[0]["numero_controle"].is_unique


def test_faixas_sao_as_esperadas(fic):
    c = fic[0]
    assert c["faixa_valor"].notna().all()
    assert set(c["faixa_negra"]) <= set(dados.FAIXAS_NEGRA) | {dados.SEM_DADO}


def test_ponte_sem_duplicatas(fic):
    assert not fic[1].duplicated().any()


def test_nomes_fficticios_nao_parecem_reais(fic):
    assert fic[0]["fornecedor"].str.contains("FICTÍCIA").all()
    assert fic[0]["orgao"].str.contains("fictício").all()


def test_mesma_semente_gera_os_mesmos_dados():
    a = dados.ficticio(n_forn=200, n_contr=500, n_socios=300)[0]
    b = dados.ficticio(n_forn=200, n_contr=500, n_socios=300)[0]
    pd.testing.assert_frame_equal(a, b)