"""Checagem do Aiven antes e durante a carga. Só leitura (a escrita é em tabela temporária).

  python checar_aiven.py                  # checagem completa, uma vez
  python checar_aiven.py --acompanhar     # uma linha a cada 20 s (Ctrl+C para parar)
  python checar_aiven.py --acompanhar --intervalo 10
"""
import argparse
import io
import statistics
import sys
import time
from datetime import datetime

import psycopg2

from config import DATABASE_URL

LIMITE_MB = 1000          # plano free-1-1gb
ORCAMENTO_MB = 600        # orçamento do projeto
TABELAS = ["dim_tempo", "dim_orgao", "dim_municipio", "dim_cnae", "dim_modalidade",
           "dim_fornecedor", "dim_socio", "ponte_empresa_socio", "fato_contrato"]


def conectar():
    return psycopg2.connect(DATABASE_URL, connect_timeout=30)


def completa():
    ok = True

    def linha(bom, texto):
        nonlocal ok
        ok &= bom
        print(f"{'OK   ' if bom else 'FALHA'} {texto}")

    t = time.perf_counter()
    try:
        con = conectar()
    except Exception as e:
        linha(False, f"conexão: {type(e).__name__}. O serviço pode estar desligado: ligue no console do Aiven.")
        return False
    con.autocommit = True
    cur = con.cursor()
    linha(True, f"conexão aberta em {(time.perf_counter() - t) * 1000:.0f} ms")

    lat = []
    for _ in range(7):
        t = time.perf_counter()
        cur.execute("SELECT 1")
        cur.fetchone()
        lat.append((time.perf_counter() - t) * 1000)
    linha(statistics.median(lat) < 500, f"latência (mediana de 7 SELECT 1): {statistics.median(lat):.0f} ms")

    cur.execute("SELECT version()")
    print("     ", cur.fetchone()[0][:60])

    cur.execute("SELECT pg_database_size(current_database())")
    mb = cur.fetchone()[0] / 1e6
    linha(mb < ORCAMENTO_MB, f"tamanho do banco: {mb:.1f} MB (orçamento {ORCAMENTO_MB} MB, limite do plano {LIMITE_MB} MB)")

    cur.execute("SELECT count(*) FROM pg_stat_activity")
    em_uso = cur.fetchone()[0]
    cur.execute("SHOW max_connections")
    maxc = int(cur.fetchone()[0])
    linha(em_uso < maxc - 3, f"conexões: {em_uso} de {maxc} (o plano free tem poucas)")

    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    existem = {r[0] for r in cur.fetchall()}
    faltam = [t for t in TABELAS if t not in existem]
    linha(not faltam, "as 9 tabelas existem" if not faltam else f"tabelas ausentes: {faltam}. Rode aplicar_schema.py")

    if not faltam:
        cheias = []
        for tab in TABELAS:
            cur.execute(f"SELECT count(*) FROM {tab}")
            n = cur.fetchone()[0]
            if n:
                cheias.append(f"{tab}={n:,}")
        if cheias:
            print("AVISO tabelas com dados (o 07 recusa; use --recarregar):", ", ".join(cheias))
        else:
            print("OK    todas as tabelas estão vazias (carga limpa)")

        cur.execute("""SELECT 1 FROM information_schema.columns
                       WHERE table_name = 'ponte_empresa_socio' AND column_name = 'elegivel'""")
        linha(bool(cur.fetchone()), "coluna ponte_empresa_socio.elegivel existe (senão o 07 a cria)")

        cur.execute("""SELECT bool_and(has_table_privilege(current_user, t, 'TRUNCATE')
                              AND has_table_privilege(current_user, t, 'INSERT'))
                       FROM unnest(%s::text[]) AS t""", (TABELAS,))
        linha(bool(cur.fetchone()[0]), "permissão de INSERT e TRUNCATE nas tabelas (precisa para --recarregar)")

    try:
        cur.execute("CREATE TEMP TABLE _teste (a int, b text)")
        cur.copy_expert("COPY _teste FROM STDIN WITH (FORMAT csv)", io.StringIO("1,x\n2,y\n"))
        cur.execute("SELECT count(*) FROM _teste")
        n = cur.fetchone()[0]
        cur.execute("DROP TABLE _teste")
        linha(n == 2, "escrita e COPY em tabela temporária")
    except Exception as e:
        linha(False, f"COPY falhou: {e}")

    con.close()
    print("\nPRONTO PARA CARREGAR" if ok else "\nHÁ PROBLEMAS: resolva antes de rodar o 07")
    return ok


def acompanhar(intervalo):
    print("hora      latência   banco     conexões   contratos no fato   (Ctrl+C para parar)")
    while True:
        h = datetime.now().strftime("%H:%M:%S")
        try:
            t = time.perf_counter()
            con = conectar()
            con.autocommit = True
            cur = con.cursor()
            cur.execute("SELECT pg_database_size(current_database()), (SELECT count(*) FROM pg_stat_activity)")
            tam, conex = cur.fetchone()
            lat = (time.perf_counter() - t) * 1000
            try:
                cur.execute("SELECT count(*) FROM fato_contrato")
                n = f"{cur.fetchone()[0]:,}"
            except Exception:
                n = "?"
            con.close()
            aviso = "  <-- PERTO DO ORÇAMENTO" if tam / 1e6 > ORCAMENTO_MB * 0.9 else ""
            print(f"{h}  {lat:6.0f} ms  {tam / 1e6:7.1f} MB  {conex:>4}      {n:>14}{aviso}", flush=True)
        except Exception as e:
            print(f"{h}  FALHA: {type(e).__name__}. Serviço desligado ou sem rede?", flush=True)
        time.sleep(intervalo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--acompanhar", action="store_true")
    ap.add_argument("--intervalo", type=int, default=20)
    a = ap.parse_args()
    if not DATABASE_URL:
        sys.exit("DATABASE_URL vazio: confira o .env")
    if a.acompanhar:
        try:
            acompanhar(a.intervalo)
        except KeyboardInterrupt:
            print("\nparado")
    else:
        sys.exit(0 if completa() else 1)


if __name__ == "__main__":
    main()