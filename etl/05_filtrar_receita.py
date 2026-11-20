"""Fase 2: filtra os arquivos da Receita, em streaming, pela lista de raízes de CNPJ do recorte.
Só as linhas dos nossos fornecedores vão para o disco (Parquet). Retomável: arquivos prontos são pulados.

Uso:
  python 05_filtrar_receita.py --teste         # só o arquivo 0 de cada grupo: valida e mede a velocidade
  python 05_filtrar_receita.py --grupo Socios  # um grupo inteiro
  python 05_filtrar_receita.py                 # tudo, mais as tabelas de domínio
  python 05_filtrar_receita.py --consolidar    # junta os Parquet e imprime volume, redução e cobertura
  python 05_filtrar_receita.py --refazer       # apaga os Parquet filtrados e refaz (use se cnpjs_raiz.csv mudou)
"""
import argparse
import csv
import hashlib
import shutil
import sys
import time

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from config import INTERIM, PROCESSED, RECEITA_URL, url_receita
from receita_stream import COLUNAS, linhas_zip

SAIDA = INTERIM / "receita_filtrada"
SAIDA.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)
METRICAS = SAIDA / "_metricas.csv"
MARCA = SAIDA / "_raizes.txt"

# Colunas mantidas (minimização, LGPD). O resto é descartado na leitura.
MANTER = {
    "Socios": ["cnpj_basico", "identificador_socio", "nome_socio", "cnpj_cpf_socio",
               "qualificacao_socio", "data_entrada_sociedade", "faixa_etaria"],
    "Empresas": ["cnpj_basico", "razao_social", "natureza_juridica", "porte", "capital_social"],
    "Estabelecimentos": ["cnpj_basico", "cnpj_ordem", "cnpj_dv", "identificador_matriz_filial",
                         "situacao_cadastral", "cnae_principal", "uf", "municipio"],
}
DOMINIO = ["Cnaes", "Municipios", "Naturezas", "Qualificacoes"]


def carregar_raizes():
    arq = INTERIM / "cnpjs_raiz.csv"
    if not arq.exists():
        sys.exit("cnpjs_raiz.csv não existe: rode 03_recorte_cnpjs.py antes")
    with arq.open(encoding="utf-8") as f:
        next(f)                                           # cabeçalho
        return {l.strip().strip('"') for l in f if l.strip()}


def gravar_parquet(destino, colunas, linhas):
    tabela = pa.table({c: pa.array([r[k] for r in linhas], type=pa.string())
                       for k, c in enumerate(colunas)})
    tmp = destino.with_name(destino.name + ".tmp")
    pq.write_table(tabela, tmp)
    tmp.replace(destino)


def processar(grupo, i, raizes):
    arquivo = f"{grupo}{i}.zip"
    destino = SAIDA / f"{grupo}_{i}.parquet"
    if destino.exists():
        print(f"{arquivo}: pulado (já processado)")
        return None
    cols, manter = COLUNAS[grupo], MANTER[grupo]
    idx = [cols.index(c) for c in manter]

    for tentativa in range(1, 4):
        contador = {"compactado": 0, "descompactado": 0}
        lidas, mantidas = 0, []
        t0 = time.time()
        try:
            for linha in linhas_zip(url_receita(arquivo), contador=contador):
                lidas += 1
                if linha.split(";", 1)[0].strip('"') in raizes:
                    row = next(csv.reader([linha], delimiter=";", quotechar='"'))
                    if len(row) != len(cols):
                        raise ValueError(f"{arquivo}: esperava {len(cols)} colunas, veio {len(row)}")
                    mantidas.append([row[j] for j in idx])
            break
        except ValueError:
            raise                                        # layout errado: não adianta tentar de novo
        except Exception as e:                           # rede, ZIP truncado etc.
            print(f"{arquivo}: tentativa {tentativa} falhou ({type(e).__name__}: {e})")
            if tentativa == 3:
                raise
            time.sleep(10 * tentativa)

    seg = time.time() - t0
    gravar_parquet(destino, manter, mantidas)
    novo = not METRICAS.exists()
    with METRICAS.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["grupo", "arquivo", "compactado", "descompactado",
                        "linhas_lidas", "linhas_mantidas", "segundos"])
        w.writerow([grupo, arquivo, contador["compactado"], contador["descompactado"],
                    lidas, len(mantidas), round(seg)])
    print(f"{arquivo}: {lidas:,} linhas lidas, {len(mantidas):,} mantidas, "
          f"{contador['compactado'] / 1e6:.0f} MB baixados em {seg:.0f}s")
    return seg


def dominio():
    for nome in DOMINIO:
        destino = SAIDA / f"dominio_{nome.lower()}.parquet"
        if destino.exists():
            continue
        rows = [r for r in csv.reader(linhas_zip(url_receita(f"{nome}.zip")),
                                      delimiter=";", quotechar='"') if r]
        if any(len(r) != 2 for r in rows):
            raise ValueError(f"{nome}: esperava 2 colunas (código e descrição)")
        gravar_parquet(destino, ["codigo", "descricao"], rows)
        print(f"{nome}: {len(rows):,} linhas")


def estimar(tempos):
    arq = INTERIM / "inventario_tamanhos.csv"
    if not arq.exists() or not tempos:
        return
    with arq.open(encoding="utf-8") as f:
        tam = {r["arquivo"]: int(r["bytes"]) for r in csv.DictReader(f)}
    print("\nestimativa para os arquivos 1 a 9 (proporcional ao tamanho de cada arquivo):")
    for g, seg in tempos.items():
        b0 = tam.get(f"{g}0.zip", 0)
        resto = sum(tam.get(f"{g}{i}.zip", 0) for i in range(1, 10))
        if b0:
            print(f"  {g}: cerca de {seg * resto / b0 / 60:.1f} min")


def consolidar():
    con = duckdb.connect()
    final = 0
    for grupo in MANTER:
        arquivos = sorted(SAIDA.glob(f"{grupo}_*.parquet"))
        if not arquivos:
            print(f"{grupo}: nenhum arquivo processado")
            continue
        padrao = (SAIDA / f"{grupo}_*.parquet").as_posix()
        destino = PROCESSED / f"{grupo.lower()}.parquet"
        con.execute(f"COPY (SELECT * FROM read_parquet('{padrao}')) TO '{destino.as_posix()}' (FORMAT PARQUET)")
        n = con.execute(f"SELECT count(*) FROM '{destino.as_posix()}'").fetchone()[0]
        final += destino.stat().st_size
        print(f"{grupo}: {len(arquivos)}/10 arquivos, {n:,} linhas, {destino.stat().st_size / 1e6:.1f} MB")
    for p in SAIDA.glob("dominio_*.parquet"):
        shutil.copy2(p, PROCESSED / p.name)

    if METRICAS.exists() and final:
        arqs, c, d, lidas, mant = con.execute(f"""
            SELECT count(*), sum(c), sum(d), sum(l), sum(m) FROM (
              SELECT arquivo, max(compactado) c, max(descompactado) d,
                     max(linhas_lidas) l, max(linhas_mantidas) m
              FROM read_csv_auto('{METRICAS.as_posix()}') GROUP BY arquivo)""").fetchone()
        print(f"\n{arqs} arquivos | baixado (compactado): {c / 1e9:.2f} GB | descompactado: {d / 1e9:.2f} GB")
        print(f"linhas lidas: {lidas:,} | mantidas: {mant:,} ({mant / lidas:.4%})")
        print(f"Parquet final: {final / 1e6:.1f} MB")
        print(f"redução sobre o descompactado: {d / final:,.0f}x | sobre o compactado: {c / final:,.0f}x")

    # cobertura: quantas raízes dos contratos foram encontradas em cada arquivo da Receita
    raizes = carregar_raizes()
    print(f"\ncobertura (raízes do recorte: {len(raizes):,}):")
    for grupo in MANTER:
        destino = PROCESSED / f"{grupo.lower()}.parquet"
        if destino.exists():
            achadas = con.execute(
                f"SELECT count(DISTINCT cnpj_basico) FROM '{destino.as_posix()}'").fetchone()[0]
            print(f"  {grupo}: {achadas:,} raízes encontradas ({achadas / len(raizes):.1%})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teste", action="store_true")
    ap.add_argument("--grupo", choices=list(MANTER))
    ap.add_argument("--consolidar", action="store_true")
    ap.add_argument("--refazer", action="store_true")
    a = ap.parse_args()

    if a.consolidar:
        return consolidar()
    if not RECEITA_URL:
        sys.exit("RECEITA_URL vazio: confira o .env")
    if a.refazer:
        for p in SAIDA.glob("*.parquet"):
            p.unlink()
        METRICAS.unlink(missing_ok=True)
        MARCA.unlink(missing_ok=True)

    raizes = carregar_raizes()
    marca = hashlib.sha1("\n".join(sorted(raizes)).encode()).hexdigest()
    if MARCA.exists() and MARCA.read_text() != marca:
        sys.exit("a lista de raízes mudou desde o último filtro: rode com --refazer "
                 "para não misturar listas diferentes")
    MARCA.write_text(marca)
    print(f"raízes de CNPJ no filtro: {len(raizes):,}")

    grupos = [a.grupo] if a.grupo else list(MANTER)
    indices = [0] if a.teste else range(10)
    tempos = {}
    for g in grupos:
        for i in indices:
            seg = processar(g, i, raizes)
            if seg is not None:
                tempos[g] = tempos.get(g, 0) + seg
    if not a.teste and not a.grupo:
        dominio()
    if a.teste:
        estimar(tempos)


if __name__ == "__main__":
    main()