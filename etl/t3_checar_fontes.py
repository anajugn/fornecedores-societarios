"""T3/S1: confere SIDRA 9605 e a API de nomes do IBGE antes de citá-los no README."""
import requests


def get(url, **kw):
    return requests.get(url, timeout=30, **kw)


r = get("https://servicodados.ibge.gov.br/api/v3/agregados/9605/metadados")
print("SIDRA 9605 metadados:", r.status_code)
if r.ok:
    m = r.json()
    print("  nome        :", m.get("nome"))
    print("  pesquisa    :", m.get("pesquisa"))
    print("  periodicidade:", m.get("periodicidade"))
    print("  níveis      :", m.get("nivelTerritorial"))
    for c in m.get("classificacoes", []):
        print("  classificação:", c.get("id"), c.get("nome"))

for nome in ("MARIA", "JOAO"):
    for sexo in ("F", "M"):
        r = get(f"https://servicodados.ibge.gov.br/api/v2/censos/nomes/{nome}", params={"sexo": sexo})
        print(f"nomes v2 {nome} sexo={sexo}:", r.status_code, (str(r.json())[:260] if r.ok else r.text[:160]))