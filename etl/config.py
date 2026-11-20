import os
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
RAW_PNCP = ROOT / "data" / "raw" / "pncp"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
for p in (RAW_PNCP, INTERIM, PROCESSED):
    p.mkdir(parents=True, exist_ok=True)

RECEITA_DIR = Path(os.getenv("RECEITA_DIR", ROOT / "data" / "raw" / "receita"))
DATABASE_URL = os.getenv("DATABASE_URL")

# Recorte (justificar por escrito no README)
DATA_INI = date.fromisoformat(os.getenv("DATA_INI", "2025-01-01"))
DATA_FIM = date.fromisoformat(os.getenv("DATA_FIM", "2025-12-31"))
VALOR_MAX = 1_000_000_000      # acima disso: erro de digitação
N_ORGAOS = 50                  # top N órgãos por valor contratado
LIMIAR_GENERO = 0.90           # RN-04

PNCP_URL = "https://pncp.gov.br/api/consulta/v1/contratos"
PNCP_PAUSA_S = 2
PNCP_PARALELO = 2