"""Seções do manual da loja, servidas por tema."""

import re
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

DATA_DIR = Path(__file__).parent / "data"

TEMAS = {
    "loja": "1. Sobre a Empório da Música",
    "horarios": "2. Horário de Funcionamento",
    "pagamento": "3. Formas de Pagamento",
    "trocas_devolucoes": "4. Política de Trocas e Devoluções",
    "frete": "5. Política de Frete e Entregas",
    "promocoes": "6. Promoções e Descontos",
    "garantia": "8. Garantia",
    "privacidade": "9. Privacidade e Proteção de Dados",
}
# Títulos completos: a lista do §7.2 tem linhas como "3. Consulta:", então uma regex genérica cortaria errado.
TITULOS = [*TEMAS.values(), "7. Atendimento via WhatsApp", "10. Disposições Finais"]

# Contradições do manual resolvidas conforme as suposições documentadas no README.
CORRECOES = [
    (r"Telefone / WhatsApp\s*\|\s*\(67\) 3341-4444", "Telefone | (67) 3341-4444\nWhatsApp | (67) 3321-4500"),
    (r"contato@empóriodamusica\.com\.br", "contato@emporiodamusica.com.br"),
    (r"Parcela mínima de R\$ 100,00", "Parcela mínima conforme as regras abaixo"),
    (r"sem valor mínimo de parcela \(exceto abaixo de R\$\s+50,00\)", "parcela mínima de R$ 50,00"),
]


def _linha_de_conteudo(linha: str) -> bool:
    return bool(linha) and not linha.startswith("Empório da Música Manual de Políticas") and not re.fullmatch(r"Página \d+", linha)


@lru_cache(maxsize=1)
def _secoes() -> dict[str, str]:
    pdf = next(DATA_DIR.glob("pol*.pdf"))  # glob: o acento do nome pode variar no git
    linhas = []
    for pagina in PdfReader(pdf).pages:
        for bruta in pagina.extract_text(extraction_mode="layout").splitlines():
            linha = re.sub(r"\s{2,}", " | ", bruta.strip())
            if _linha_de_conteudo(linha):
                linhas.append(linha)

    secoes: dict[str, list[str]] = {}
    atual = None
    for linha in linhas:
        if linha in TITULOS:
            atual = linha
            secoes[atual] = []
        elif atual:
            secoes[atual].append(linha)

    textos = {}
    for titulo, conteudo in secoes.items():
        texto = "\n".join(conteudo)
        for padrao, novo in CORRECOES:
            texto = re.sub(padrao, novo, texto)
        textos[titulo] = texto
    return textos


def get_policy(tema: str) -> str:
    return _secoes()[TEMAS[tema]]
