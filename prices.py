import logging
from datetime import timedelta

import yfinance as yf

logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# (rótulo exibido, símbolo Yahoo Finance)
# Ibovespa e S&P 500 são índices (pontos); demais são cotados em dólar.
ASSETS: list[tuple[str, str]] = [
    ("Ibovespa",         "^BVSP"),
    ("S&P 500",          "^GSPC"),
    ("Bitcoin",          "BTC-USD"),
    ("Ethereum",         "ETH-USD"),
    ("Ouro",             "GC=F"),
    ("Petróleo (Brent)", "BZ=F"),
]

# Janelas de variação exibidas no painel (em dias corridos)
JANELAS = (3, 7, 30)


def _variacao(pares: list[tuple], dias: int) -> float | None:
    """Variação % entre o último fechamento e o fechamento de `dias` atrás.

    Usa o pregão disponível mais próximo <= (data atual - dias), tolerando
    fins de semana e feriados sem dado.
    """
    if not pares:
        return None
    ult_data, atual = pares[-1]
    alvo = ult_data - timedelta(days=dias)
    base = None
    for data, valor in pares:
        if data <= alvo:
            base = valor
        else:
            break
    if base is None or base == 0:
        return None
    return (atual / base - 1) * 100


def obter_precos() -> list[dict]:
    """Busca preço atual e variações dos ativos do painel.

    Cada ativo é isolado em try/except: uma falha pontual no Yahoo nunca
    derruba o painel inteiro — o ativo entra com valores None ("—").
    """
    resultados: list[dict] = []
    for nome, simbolo in ASSETS:
        try:
            hist   = yf.Ticker(simbolo).history(period="2mo", interval="1d", auto_adjust=False)
            closes = hist["Close"].dropna()
            if closes.empty:
                raise ValueError("sem dados retornados pelo Yahoo")

            pares = [(ts.date(), float(v)) for ts, v in closes.items()]
            atual = pares[-1][1]
            resultados.append({
                "nome":    nome,
                "preco":   atual,
                "var_3d":  _variacao(pares, 3),
                "var_7d":  _variacao(pares, 7),
                "var_30d": _variacao(pares, 30),
            })
        except Exception as e:
            print(f"   ⚠️  preço indisponível [{nome}]: {e}")
            resultados.append({
                "nome": nome, "preco": None,
                "var_3d": None, "var_7d": None, "var_30d": None,
            })
    return resultados
