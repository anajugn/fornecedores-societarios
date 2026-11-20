"""Testes unitários de genero.py (RN-04) e do 06_classificar_empresas.py (RN-03 e RN-05).
Dados sintéticos: sem rede, sem banco, sem tocar em data/.

Uso:  python -m pytest tests/test_unitarios.py -v
"""
import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etl"))

import genero  # noqa: E402

m06 = importlib.import_module("06_classificar_empresas")


# ================================================================ genero.py
def test_normalizar_nome_tira_acento_pontuacao_e_caixa():
    assert genero.normalizar_nome("  joão-pedro d'Ávila ") == "JOAO PEDRO D AVILA"


@pytest.mark.parametrize("nome,esperado", [
    ("maria da silva", "MARIA"), ("  JOSÉ  ", "JOSE"), ("Ana-Júlia Souza", "ANA"), ("", ""),
])
def test_primeiro_nome(nome, esperado):
    assert genero.primeiro_nome(nome) == esperado


CACHE = {
    "MARIA": {"F": 1000, "M": 10},
    "ALEX": {"F": 500, "M": 500},
    "SEM": {"F": 0, "M": 0},
    "LIM90": {"F": 90, "M": 10},
    "LIM89": {"F": 89, "M": 11},
    "JOAO": {"F": 10, "M": 990},
}


@pytest.mark.parametrize("nome,esperado", [
    ("MARIA", "F"),
    ("JOAO", "M"),
    ("ALEX", "I_ambiguo"),
    ("SEM", "I_ausente"),          # IBGE sem registro
    ("DESCONHECIDO", "I_ausente"),  # fora do cache
    ("LIM90", "F"),                # exatamente 90%: o limiar é inclusivo
    ("LIM89", "I_ambiguo"),        # 89%: abaixo do limiar
])
def test_classificar_com_limiar_de_90(nome, esperado):
    assert genero.classificar(nome, CACHE, 0.90) == esperado


def test_limiar_mais_alto_torna_mais_nomes_indeterminados():
    assert genero.classificar("LIM90", CACHE, 0.95) == "I_ambiguo"
    assert genero.classificar("LIM90", CACHE, 0.80) == "F"


def test_confianca():
    assert genero.confianca("MARIA", CACHE) == pytest.approx(1000 / 1010)
    assert genero.confianca("ALEX", CACHE) == pytest.approx(0.5)
    assert genero.confianca("SEM", CACHE) == 0.0
    assert genero.confianca("DESCONHECIDO", CACHE) == 0.0


def test_consultar_soma_frequencias_e_zera_nomes_ausentes(monkeypatch):
    resposta = [{"nome": "maria", "res": [{"periodo": "1930[", "frequencia": 5},
                                          {"periodo": "1940[", "frequencia": 10}]}]
    monkeypatch.setattr(genero, "_get", lambda url, params: resposta)
    assert genero._consultar(["MARIA", "ZZZ"], "F") == {"MARIA": 15, "ZZZ": 0}


def test_consultar_rejeita_resposta_que_nao_e_lista(monkeypatch):
    monkeypatch.setattr(genero, "_get", lambda url, params: {"erro": "x"})
    with pytest.raises(ValueError):
        genero._consultar(["MARIA"], "F")


def test_completar_cache_consulta_so_o_que_falta(monkeypatch, tmp_path):
    chamadas = []

    def falso(nomes, sexo):
        chamadas.append(tuple(nomes))
        return {n: 7 for n in nomes}

    monkeypatch.setattr(genero, "CACHE", tmp_path / "cache.json")   # não toca no cache real
    monkeypatch.setattr(genero, "consultar", falso)
    monkeypatch.setattr(genero.time, "sleep", lambda s: None)

    cache = {"ANA": {"F": 1, "M": 1}}
    assert genero.completar_cache(["ANA", "BIA", "CAIO"], cache) == 2
    assert cache["ANA"] == {"F": 1, "M": 1}
    assert cache["BIA"] == {"F": 7, "M": 7}
    assert all("ANA" not in nomes for nomes in chamadas)
    assert (tmp_path / "cache.json").exists()

    chamadas.clear()
    assert genero.completar_cache(["ANA", "BIA", "CAIO"], cache) == 0   # tudo em cache: nenhuma chamada
    assert chamadas == []


# ================================================================ 06: RN-03
def test_sem_acento():
    assert m06.sem_acento("Sócio-Administrador") == "SOCIO-ADMINISTRADOR"
    assert m06.sem_acento("Mãe") == "MAE"


@pytest.mark.parametrize("desc,excluido", [
    ("PROCURADOR", True), ("REPRESENTANTE LEGAL", True), ("INVENTARIANTE", True),
    ("LIQUIDANTE", True), ("MAE", True), ("PAI", True),
    ("SOCIO", False), ("SOCIO-ADMINISTRADOR", False), ("DIRETOR", False),
])
def test_qualificacoes_que_nao_contam_como_socio(desc, excluido):
    assert bool(m06.EXCLUIR.search(desc)) is excluido


@pytest.mark.parametrize("desc,admin", [
    ("DIRETOR", True), ("PRESIDENTE", True), ("CONSELHEIRO DE ADMINISTRACAO", True),
    ("ADMINISTRADOR", True),
    ("SOCIO-ADMINISTRADOR", False),   # sócio de fato: continua contando na regra estrita
    ("SOCIO", False), ("PROCURADOR", False),
])
def test_qualificacoes_de_administrador(desc, admin):
    assert bool(m06.ADMIN.search(desc)) is admin


# ================================================================ 06: RN-05
F = ("PF", "F", True)
M = ("PF", "M", True)
I = ("PF", "I", True)
PJ = ("PJ", "I", False)
M_NAO_ELEGIVEL = ("PF", "M", False)

CASOS = {
    "00000001": [F, F, M],            # 2 de 3 são F
    "00000002": [F, M, M],
    "00000003": [F, M],               # empate: sem maioria
    "00000004": [F, F, I],            # exatamente 1/3 indeterminado: ainda classifica
    "00000005": [F, I, I],            # mais de 1/3 indeterminado
    "00000006": [F, F, PJ],           # sócio PJ vence a maioria
    "00000007": [],                   # nenhum sócio
    "00000008": [PJ],                 # só PJ: misto, não 'sem sócio'
    "00000009": [F, M_NAO_ELEGIVEL],  # o homem não é elegível (ex.: procurador)
    "00000010": [F, I],
}
MOTIVO = {
    "00000001": "maioria_f", "00000002": "maioria_m", "00000003": "sem_maioria",
    "00000004": "maioria_f", "00000005": "indeterminados", "00000006": "socio_pj",
    "00000007": "sem_socio", "00000008": "socio_pj", "00000009": "maioria_f",
    "00000010": "indeterminados",
}


def montar(casos):
    linhas = [(c, t, g, e) for c, v in casos.items() for t, g, e in v]
    s = pd.DataFrame(linhas, columns=["cnpj_basico", "tipo", "genero", "elegivel"])
    empresas = pd.DataFrame({"cnpj_basico": list(casos)})
    return empresas, s.drop(columns="elegivel"), s["elegivel"]


@pytest.fixture(scope="module")
def resultado():
    empresas, socios, el = montar(CASOS)
    return m06.classificar_empresas(empresas, socios, el).set_index("cnpj_basico")


def test_motivo_de_cada_caso(resultado):
    obtido = resultado["motivo"].to_dict()
    assert obtido == MOTIVO


def test_classe_de_controle_de_cada_caso(resultado):
    classe = resultado["classificacao_controle"]
    assert classe["00000001"] == "feminino"
    assert classe["00000002"] == "masculino"
    assert classe["00000003"] == "misto_indeterminado"
    assert classe["00000005"] == "misto_indeterminado"
    assert classe["00000006"] == "misto_indeterminado"
    assert classe["00000007"] == "sem_socio"
    assert classe["00000008"] == "misto_indeterminado"


def test_contagens_de_socios(resultado):
    assert resultado.loc["00000006", "n_socios_total"] == 3
    assert resultado.loc["00000006", "n_socios_elegiveis"] == 2
    assert resultado.loc["00000009", "n_socios_total"] == 2
    assert resultado.loc["00000009", "n_socios_elegiveis"] == 1
    assert resultado.loc["00000008", "n_socios_elegiveis"] == 0
    assert bool(resultado.loc["00000008", "tem_socio_pj"]) is True
    assert bool(resultado.loc["00000001", "tem_socio_pj"]) is False


def test_pct_indeterminados(resultado):
    assert resultado.loc["00000004", "pct_indeterminados"] == pytest.approx(33.33)
    assert resultado.loc["00000005", "pct_indeterminados"] == pytest.approx(66.67)
    assert resultado.loc["00000007", "pct_indeterminados"] == 0


def test_regra_estrita_pode_inverter_o_controle():
    """Uma sócia e dois diretores homens: a regra padrão dá masculino; a estrita, feminino."""
    casos = {"00000001": [F, M, M]}
    empresas, socios, _ = montar(casos)
    padrao = pd.Series([True, True, True], index=socios.index)
    estrita = pd.Series([True, False, False], index=socios.index)   # diretores saem
    r_padrao = m06.classificar_empresas(empresas, socios, padrao).iloc[0]
    r_estrita = m06.classificar_empresas(empresas, socios, estrita).iloc[0]
    assert r_padrao["classificacao_controle"] == "masculino"
    assert r_estrita["classificacao_controle"] == "feminino"