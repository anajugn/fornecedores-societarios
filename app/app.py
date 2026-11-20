"""Painel Streamlit: quem está por trás dos CNPJs que recebem dinheiro público.

Fonte dos dados (variável de ambiente ou segredo do Streamlit Cloud):
  PAINEL_FONTE = ficticio (padrão) | banco
  DATABASE_URL = conexão do Aiven (só no modo banco)

Uso:  streamlit run app/app.py
"""
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dados  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

MIN_N = 5                       # RN-09: nenhum recorte com menos de 5 fornecedores
TETO = 100_000_000              # R$ 100 mi (KPI com e sem contratos gigantes)
ACENTO, APAGADO = "#1f6f8b", "#c4ccd2"
CLASSES, ROTULO, FAIXAS_NEGRA = dados.CLASSES, dados.ROTULO, dados.FAIXAS_NEGRA
INVERSO = {v: k for k, v in ROTULO.items()}
METRICAS = ["Valor contratado", "Número de contratos", "Valor mediano do contrato"]
INFO = {                        # coluna agregada, divisor para o eixo, rótulo do eixo
    "Valor contratado": ("soma", 1e6, "R$ milhões"),
    "Número de contratos": ("n_contratos", 1, "contratos"),
    "Valor mediano do contrato": ("mediana", 1e3, "R$ mil"),
}

st.set_page_config(page_title="Fornecedores societários", layout="wide")


def _config(nome, padrao=""):
    try:
        if nome in st.secrets:
            return str(st.secrets[nome])
    except Exception:
        pass
    return os.getenv(nome, padrao)


# ------------------------------------------------------------------ formatação (pt-BR)
def _ptbr(s):
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(v):
    if v is None or pd.isna(v):
        return "—"
    for lim, suf in ((1e12, "tri"), (1e9, "bi"), (1e6, "mi"), (1e3, "mil")):
        if abs(v) >= lim:
            return "R$ " + _ptbr(f"{v / lim:,.2f}") + f" {suf}"
    return "R$ " + _ptbr(f"{v:,.2f}")


def pct(v, casas=1):
    return "—" if v is None or pd.isna(v) else _ptbr(f"{v:.{casas}f}") + "%"


def inteiro(v):
    return _ptbr(f"{int(v):,}")


def txt_metrica(v, metrica):
    return inteiro(v) if metrica == "Número de contratos" else brl(v)


# ------------------------------------------------------------------ dados
FONTE = _config("PAINEL_FONTE", "ficticio").lower()


@st.cache_data(ttl=3600, show_spinner="Carregando os dados...")
def carregar(fonte, url):
    return dados.carregar(fonte, url)


try:
    contratos, ponte = carregar(FONTE, _config("DATABASE_URL"))
except Exception as erro:
    st.error(f"Não consegui carregar os dados (fonte: {FONTE}): {erro}")
    st.info("No modo banco, confira se o serviço do Aiven está ligado (o plano gratuito desliga por "
            "inatividade) e se a DATABASE_URL está correta.")
    st.stop()

# ------------------------------------------------------------------ seleção por clique (filtro cruzado)
if "reset" not in st.session_state:
    st.session_state["reset"] = 0
K_CLASSE = f"sel_classe_{st.session_state['reset']}"
K_UF = f"sel_uf_{st.session_state['reset']}"


def selecionados(chave):
    try:
        pontos = st.session_state[chave]["selection"]["points"]
    except (KeyError, TypeError, AttributeError):
        return []
    return [p["x"] for p in pontos if "x" in p]


sel_classe = [INVERSO[x] for x in selecionados(K_CLASSE) if x in INVERSO]
sel_uf = [str(x) for x in selecionados(K_UF)]

# ------------------------------------------------------------------ barra lateral
st.sidebar.header("Métrica")
metrica = st.sidebar.radio("Métrica dos gráficos", METRICAS,
                           help="Vale para todos os gráficos das abas. Os KPIs do topo não mudam.")
st.sidebar.header("Filtros")
st.sidebar.caption("Campo vazio = sem filtro. Clicar nas barras da aba Gênero também filtra.")
f_uf_org = st.sidebar.multiselect("UF do órgão", sorted(contratos["uf_orgao"].unique()))
f_uf_for = st.sidebar.multiselect("UF do fornecedor", sorted(contratos["uf_fornecedor"].unique()))
f_orgao = st.sidebar.multiselect("Órgão", sorted(contratos["orgao"].unique()))
f_porte = st.sidebar.multiselect("Porte do fornecedor", sorted(contratos["porte"].unique()))
f_faixa = st.sidebar.multiselect("Faixa de valor do contrato", dados.FAIXAS_VALOR)
f_meses = st.sidebar.slider("Meses de assinatura", 1, 12, (1, 12))


def filtrar(ignorar=()):
    """Aplica todos os filtros. `ignorar` deixa de fora a seleção por clique do próprio gráfico."""
    d = contratos
    m = d["mes"].between(*f_meses)
    if f_uf_org:
        m &= d["uf_orgao"].isin(f_uf_org)
    if f_uf_for:
        m &= d["uf_fornecedor"].isin(f_uf_for)
    if f_orgao:
        m &= d["orgao"].isin(f_orgao)
    if f_porte:
        m &= d["porte"].isin(f_porte)
    if f_faixa:
        m &= d["faixa_valor"].isin(f_faixa)
    if "classe" not in ignorar and sel_classe:
        m &= d["classe"].isin(sel_classe)
    if "uf" not in ignorar and sel_uf:
        m &= d["uf_fornecedor"].isin(sel_uf)
    return d[m]


if sel_classe or sel_uf:
    st.sidebar.markdown("**Seleção por clique ativa**")
    if sel_classe:
        st.sidebar.caption("Gênero do controle: " + ", ".join(ROTULO[c] for c in sel_classe))
    if sel_uf:
        st.sidebar.caption("UF do fornecedor: " + ", ".join(sel_uf))
    if st.sidebar.button("Limpar seleção dos gráficos"):
        st.session_state["reset"] += 1
        st.rerun()


# ------------------------------------------------------------------ cálculos
def agregar(d, por):
    return (d.groupby(por, observed=True)
            .agg(n_contratos=("valor", "size"), n_fornecedores=("cnpj_raiz", "nunique"),
                 soma=("valor", "sum"), mediana=("valor", "median"))
            .reset_index())


def indicador_fem(g, metrica):
    """Participação feminina entre os de controle definido (feminino + masculino)."""
    f = g.loc[g["classe"] == "feminino", "valor"]
    m = g.loc[g["classe"] == "masculino", "valor"]
    if metrica == "Número de contratos":
        t = len(f) + len(m)
        return 100 * len(f) / t if t else np.nan
    if metrica == "Valor contratado":
        t = f.sum() + m.sum()
        return 100 * f.sum() / t if t else np.nan
    return f.median() / m.median() if len(f) and len(m) else np.nan       # razão F ÷ M


def eixo_ind(metrica):
    return {"Valor contratado": "% do valor com controle feminino",
            "Número de contratos": "% dos contratos com controle feminino",
            "Valor mediano do contrato": "razão das medianas (feminino ÷ masculino)"}[metrica]


def fmt_ind(v, metrica):
    if metrica == "Valor mediano do contrato":
        return _ptbr(f"{v:.2f}") + "×"
    return pct(v)


def por_grupo(d, por, metrica):
    """Indicador feminino por grupo; grupos com menos de MIN_N fornecedores ficam de fora (RN-09)."""
    dd = d[d["classe"].isin(["feminino", "masculino"])]
    linhas, ocultos = [], 0
    for chave, g in dd.groupby(por):
        nf = g["cnpj_raiz"].nunique()
        if nf < MIN_N:
            ocultos += 1
            continue
        linhas.append({"grupo": chave, "ind": indicador_fem(g, metrica), "n_fornecedores": nf})
    tab = pd.DataFrame(linhas, columns=["grupo", "ind", "n_fornecedores"]).dropna(subset=["ind"])
    return tab, ocultos


def pct_fem(d, por="valor"):
    dd = d[d["classe"].isin(["feminino", "masculino"])]
    if dd["cnpj_raiz"].nunique() < MIN_N:
        return np.nan
    f = dd[dd["classe"] == "feminino"]
    return 100 * f["valor"].sum() / dd["valor"].sum() if por == "valor" else 100 * len(f) / len(dd)


def barras(x, y, textos, cores, titulo_y, altura=340):
    fig = go.Figure(go.Bar(x=list(x), y=list(y), text=list(textos), textposition="outside",
                           marker_color=list(cores), cliponaxis=False,
                           hovertemplate="%{x}<br>%{text}<extra></extra>"))
    fig.update_layout(yaxis_title=titulo_y, xaxis_title=None, height=altura, showlegend=False,
                      margin=dict(t=30, b=10, l=10, r=10), dragmode=False)
    return fig


def resumo(d, por, nome):
    linhas, ocultos = [], 0
    for chave, g in d.groupby(por):
        nf = g["cnpj_raiz"].nunique()
        if nf < MIN_N:
            ocultos += 1
            continue
        p = pct_fem(g)
        linhas.append({nome: chave, "Contratos": len(g), "Fornecedores": nf,
                       "Valor total (R$ mi)": round(g["valor"].sum() / 1e6, 2),
                       "Mediana (R$ mil)": round(g["valor"].median() / 1e3, 1),
                       "% valor feminino": round(p, 1) if pd.notna(p) else None})
    tab = pd.DataFrame(linhas)
    if not tab.empty:
        tab = tab.sort_values("Valor total (R$ mi)", ascending=False)
    return tab, ocultos


# ------------------------------------------------------------------ cabeçalho
st.title("Quem está por trás dos CNPJs que recebem dinheiro público")
if FONTE == "banco":
    st.caption("Fonte: PostgreSQL do Aiven (contratos do PNCP de 2025 cruzados com o quadro societário da "
               "Receita Federal). Gênero inferido pelo primeiro nome; cor/raça é proxy territorial.")
else:
    st.warning("**DADOS FICTÍCIOS.** Este painel está rodando com dados sintéticos só para testar a "
               "interface. Nenhum número aqui descreve contratos ou empresas reais.")

d = filtrar()
if d.empty:
    st.info("Nenhum contrato com esses filtros.")
    st.stop()
if d["cnpj_raiz"].nunique() < MIN_N:
    st.warning(f"O recorte tem menos de {MIN_N} fornecedores. Os indicadores ficam ocultos para evitar "
               "reidentificação (RN-09). Amplie os filtros.")
    st.stop()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Contratos", inteiro(len(d)))
k2.metric("Fornecedores", inteiro(d["cnpj_raiz"].nunique()))
k3.metric("Valor contratado", brl(d["valor"].sum()),
          help="Valor global dos contratos (o que foi contratado, não o que foi pago).")
k4.metric("Valor mediano do contrato", brl(d["valor"].median()))

t1, t2, t3, t4 = st.tabs(["Gênero do controle (Q1)", "Interseccional (Q2)",
                          "Concentração (Q3)", "Drill-down"])

# ------------------------------------------------------------------ Q1
with t1:
    definido = d[d["classe"].isin(["feminino", "masculino"])]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valor com controle feminino", pct(pct_fem(d)),
              help="Entre as empresas com controle definido (feminino ou masculino).")
    c2.metric("O mesmo, sem contratos acima de R$ 100 mi", pct(pct_fem(d[d["valor"] <= TETO])),
              help="Poucos contratos gigantes concentram boa parte do valor; este número os retira.")
    c3.metric("Contratos com controle feminino", pct(pct_fem(d, "contratos")))
    c4.metric("Valor com controle definido",
              pct(100 * definido["valor"].sum() / d["valor"].sum()),
              help="Feminino + masculino. O restante é misto/indeterminado ou sem sócio elegível.")

    esq, dir_ = st.columns(2)
    with esq:
        st.subheader(f"{metrica}, por gênero do controle")
        st.caption("Clique nas barras para filtrar o painel.")
        df_a = filtrar(ignorar=("classe",))
        agr = agregar(df_a, "classe").set_index("classe").reindex(CLASSES)
        nf = agr["n_fornecedores"].fillna(0)
        col, div, rot = INFO[metrica]
        vis = [c for c in CLASSES if nf[c] >= MIN_N]
        if vis:
            cores = [ACENTO if (not sel_classe or c in sel_classe) else APAGADO for c in vis]
            fig = barras([ROTULO[c] for c in vis], [agr.loc[c, col] / div for c in vis],
                         [txt_metrica(agr.loc[c, col], metrica) for c in vis], cores, rot)
            st.plotly_chart(fig, key=K_CLASSE, on_select="rerun", selection_mode="points")
        else:
            st.info("Nenhuma classe com fornecedores suficientes.")
        ocultas = int(nf.between(1, MIN_N - 1).sum())
        if ocultas:
            st.caption(f"{ocultas} classe(s) ocultas por terem menos de {MIN_N} fornecedores.")
    with dir_:
        st.subheader(f"{eixo_ind(metrica).capitalize()}, por UF do fornecedor")
        st.caption("Só empresas de controle definido. Clique nas barras para filtrar.")
        df_b = filtrar(ignorar=("uf",))
        tab, ocultos = por_grupo(df_b, "uf_fornecedor", metrica)
        if tab.empty:
            st.info("Nenhuma UF com fornecedores suficientes.")
        else:
            tab = tab.sort_values("ind", ascending=False)
            cores = [ACENTO if (not sel_uf or u in sel_uf) else APAGADO for u in tab["grupo"]]
            fig = barras(tab["grupo"], tab["ind"], [fmt_ind(v, metrica) for v in tab["ind"]],
                         cores, eixo_ind(metrica))
            if metrica == "Valor mediano do contrato":
                fig.add_hline(y=1, line_dash="dot", line_color="#888")
            st.plotly_chart(fig, key=K_UF, on_select="rerun", selection_mode="points")
        if ocultos:
            st.caption(f"{ocultos} UF(s) ocultas por terem menos de {MIN_N} fornecedores de controle definido.")

# ------------------------------------------------------------------ Q2
with t2:
    st.info("**Leitura cuidadosa.** O percentual de pretos e pardos é o do **município do fornecedor** "
            "(Censo 2022), não o do sócio. Isto é um proxy territorial: nada aqui diz a cor ou raça de "
            "ninguém, e qualquer leitura individual seria falácia ecológica.")
    dd = d[d["faixa_negra"] != dados.SEM_DADO]
    sem = len(d) - len(dd)
    if sem:
        st.caption(f"{inteiro(sem)} contratos sem município traduzido ficam fora desta aba.")
    esq, dir_ = st.columns(2)
    with esq:
        st.subheader(f"{eixo_ind(metrica).capitalize()}, por composição racial do município")
        tab, ocultos = por_grupo(dd, "faixa_negra", metrica)
        if tab.empty:
            st.info("Nenhuma faixa com fornecedores suficientes.")
        else:
            ordem = {f: i for i, f in enumerate(FAIXAS_NEGRA)}
            tab = tab.sort_values("grupo", key=lambda s: s.map(ordem))
            fig = barras(tab["grupo"], tab["ind"], [fmt_ind(v, metrica) for v in tab["ind"]],
                         [ACENTO] * len(tab), eixo_ind(metrica))
            fig.update_layout(xaxis_title="% de pretos e pardos no município do fornecedor")
            if metrica == "Valor mediano do contrato":
                fig.add_hline(y=1, line_dash="dot", line_color="#888")
            st.plotly_chart(fig)
        if ocultos:
            st.caption(f"{ocultos} faixa(s) ocultas por terem menos de {MIN_N} fornecedores.")
    with dir_:
        st.subheader(f"{metrica}: faixa racial × gênero do controle")
        agr = agregar(dd, ["faixa_negra", "classe"])
        agr = agr[agr["n_fornecedores"] >= MIN_N]
        if agr.empty:
            st.info("Nenhuma célula com fornecedores suficientes.")
        else:
            col, div, rot = INFO[metrica]
            bruto = agr.pivot(index="faixa_negra", columns="classe", values=col).reindex(
                index=FAIXAS_NEGRA, columns=CLASSES)
            texto = [["" if pd.isna(v) else txt_metrica(v, metrica) for v in linha]
                     for linha in bruto.to_numpy()]
            fig = go.Figure(go.Heatmap(
                z=(bruto / div).to_numpy(), x=[ROTULO[c] for c in CLASSES], y=FAIXAS_NEGRA,
                text=texto, texttemplate="%{text}", colorscale="Blues", showscale=False,
                hoverongaps=False, hovertemplate="%{y} | %{x}<br>%{text}<extra></extra>"))
            fig.update_yaxes(autorange="reversed", title="% de pretos e pardos no município")
            fig.update_layout(height=340, margin=dict(t=30, b=10, l=10, r=10))
            st.plotly_chart(fig)
            st.caption(f"Células com menos de {MIN_N} fornecedores ficam em branco.")

# ------------------------------------------------------------------ Q3
with t3:
    st.subheader("Concentração do valor entre fornecedores")
    s = d.groupby("cnpj_raiz")["valor"].sum().sort_values()
    n, total, v = len(s), float(s.sum()), s.to_numpy()
    gini = 2 * np.sum(np.arange(1, n + 1) * v) / (n * total) - (n + 1) / n
    top10 = v[::-1][:10].sum() / total
    k1pct = max(1, round(n * 0.01))
    top1 = v[::-1][:k1pct].sum() / total
    hhi = float(((v / total) ** 2).sum() * 10_000)
    a, b, c, e = st.columns(4)
    a.metric("10 maiores fornecedores", pct(100 * top10), help="Parcela do valor contratado.")
    b.metric(f"1% maiores ({k1pct} fornecedores)", pct(100 * top1))
    c.metric("Índice de Gini", _ptbr(f"{gini:.3f}"), help="0 = valor igual para todos; 1 = tudo em um só.")
    e.metric("HHI", inteiro(hhi), help="Herfindahl-Hirschman, de 0 a 10.000. Abaixo de 1.500 é pouco concentrado.")

    acum = np.concatenate([[0.0], np.cumsum(v) / total])
    x = np.arange(0, n + 1) / n
    idx = np.unique(np.linspace(0, n, min(n + 1, 400)).astype(int))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x[idx] * 100, y=acum[idx] * 100, mode="lines", name="Fornecedores",
                             line=dict(color=ACENTO)))
    fig.add_trace(go.Scatter(x=[0, 100], y=[0, 100], mode="lines", name="Distribuição igual",
                             line=dict(color=APAGADO, dash="dot")))
    fig.update_layout(xaxis_title="% dos fornecedores (do menor para o maior)",
                      yaxis_title="% acumulado do valor", height=340,
                      margin=dict(t=30, b=10, l=10, r=10), legend=dict(orientation="h"))
    esq, dir_ = st.columns([3, 2])
    with esq:
        st.plotly_chart(fig)
    with dir_:
        st.markdown("**Maiores fornecedores por valor**")
        nomes = d.drop_duplicates("cnpj_raiz").set_index("cnpj_raiz")["fornecedor"]
        top = s.sort_values(ascending=False).head(10)
        st.dataframe(pd.DataFrame({"Fornecedor": nomes.reindex(top.index).to_numpy(),
                                   "Valor (R$ mi)": (top.to_numpy() / 1e6).round(2),
                                   "% do total": (100 * top.to_numpy() / total).round(2)}),
                     hide_index=True)
        st.caption("Empresas e valores são públicos (PNCP). O gênero do controle não aparece por empresa.")

    st.subheader("Concentração societária (RN-07)")
    p = ponte[ponte["cnpj_raiz"].isin(set(d["cnpj_raiz"]))]
    if p.empty:
        st.info("Sem vínculos de sócios elegíveis neste recorte.")
    else:
        por_socio = p.groupby("sk_socio")["cnpj_raiz"].nunique()
        multi = por_socio[por_socio >= 2].index
        firmas = p[p["sk_socio"].isin(multi)]["cnpj_raiz"].nunique()
        a, b, c = st.columns(3)
        a.metric("Sócios elegíveis", inteiro(len(por_socio)))
        b.metric("Sócios em 2+ fornecedores", pct(100 * len(multi) / len(por_socio)))
        c.metric("Fornecedores que dividem sócio", pct(100 * firmas / p["cnpj_raiz"].nunique()))
        dist = por_socio.clip(upper=5).value_counts().sort_index()
        dist = dist[dist >= MIN_N]
        rot = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5 ou mais"}
        fig = go.Figure(go.Bar(x=[rot[i] for i in dist.index], y=dist.to_numpy(),
                               text=[inteiro(q) for q in dist], textposition="outside",
                               marker_color=ACENTO, cliponaxis=False))
        fig.update_layout(xaxis_title="Fornecedores do recorte em que o sócio aparece",
                          yaxis_title="sócios", height=300, margin=dict(t=30, b=10, l=10, r=10))
        st.plotly_chart(fig)
        st.caption("Conta só os fornecedores do recorte (50 órgãos), então subestima a rede real do sócio. "
                   "Sócios aparecem por identificador anônimo.")

# ------------------------------------------------------------------ drill-down
with t4:
    st.subheader("Do estado ao contrato")
    st.caption(f"Níveis: UF do órgão, depois órgão, depois os maiores contratos. Grupos com menos de {MIN_N} "
               "fornecedores não aparecem (RN-09), e a classe de controle nunca é mostrada por empresa.")
    ufs = sorted(d["uf_orgao"].unique())
    uf_sel = st.selectbox("UF do órgão", ["Todas"] + ufs)
    if uf_sel == "Todas":
        tab, ocultos = resumo(d, "uf_orgao", "UF do órgão")
        if tab.empty:
            st.info("Nenhuma UF com fornecedores suficientes.")
        else:
            st.dataframe(tab, hide_index=True)
        if ocultos:
            st.caption(f"{ocultos} UF(s) ocultas (menos de {MIN_N} fornecedores).")
    else:
        d1 = d[d["uf_orgao"] == uf_sel]
        org_sel = st.selectbox("Órgão", ["Todos"] + sorted(d1["orgao"].unique()))
        if org_sel == "Todos":
            tab, ocultos = resumo(d1, "orgao", "Órgão")
            if tab.empty:
                st.info("Nenhum órgão com fornecedores suficientes nesta UF.")
            else:
                st.dataframe(tab, hide_index=True)
            if ocultos:
                st.caption(f"{ocultos} órgão(s) ocultos (menos de {MIN_N} fornecedores).")
        else:
            d2 = d1[d1["orgao"] == org_sel]
            if d2["cnpj_raiz"].nunique() < MIN_N:
                st.info(f"Este órgão tem menos de {MIN_N} fornecedores no recorte: detalhe oculto (RN-09).")
            else:
                st.markdown(f"**50 maiores contratos de {org_sel}** ({inteiro(len(d2))} no recorte)")
                top = d2.sort_values("valor", ascending=False).head(50)
                st.dataframe(pd.DataFrame({
                    "Data": top["data"].dt.strftime("%d/%m/%Y"), "Fornecedor": top["fornecedor"],
                    "Porte": top["porte"], "UF do fornecedor": top["uf_fornecedor"],
                    "Modalidade": top["modalidade"], "Valor (R$)": top["valor"].round(2),
                    "Nº de controle": top["numero_controle"]}), hide_index=True)

st.divider()
st.caption("Limitações: `valor_global` é o valor contratado, não o pago; anulações não são identificáveis; "
           "gênero vem do primeiro nome (Censo 2010) e pode errar; cor/raça é proxy territorial. "
           "Detalhes no README, seção 9.")