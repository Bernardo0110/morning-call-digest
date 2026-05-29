from google.genai import types

from config import MAX_TRANSCRIPT_CHARS, MODEL, client

_PROMPT_RESUMO = """
Você é um analista de mercado. Recebeu as transcrições de {n_canais} morning calls
de {data} dos canais: {canais_presentes}.

{aviso_ausentes}

Escreva um resumo executivo em exatamente 3 a 4 parágrafos para ser enviado por email
a um investidor que não teve tempo de assistir os vídeos.

REGRAS:
- Use APENAS informações explicitamente presentes nas transcrições. NUNCA invente.
- Sempre atribua informações ao canal: "Segundo o BTG...", "A Genial destaca..."
- Consenso: "Há consenso entre [canais] de que..."
- Divergência: "Enquanto [canal1] vê X, [canal2] aponta Y."
- Se canais estiverem ausentes, mencione no primeiro parágrafo.
- Priorize: cenário macro, movimentos de mercado, ativos em destaque, riscos.
- Sem bullet points, sem títulos, apenas texto corrido.
- Não comece com "Bom dia" ou introduções genéricas.

TRANSCRIÇÕES:
---
{transcricoes}
---

Escreva o resumo agora:
"""


def gerar_resumo(
    transcricoes: dict[str, str],
    ausentes: dict[str, str],
    data_ref: str,
) -> str:
    blocos = "\n\n".join(
        f'[{canal.upper()}]\n{texto[:MAX_TRANSCRIPT_CHARS]}'
        + ("...[truncado]" if len(texto) > MAX_TRANSCRIPT_CHARS else "")
        for canal, texto in transcricoes.items()
    )

    if ausentes:
        linhas = "\n".join(f"- {c.upper()}: {m}" for c, m in ausentes.items())
        aviso  = (
            f"ATENÇÃO: Os seguintes canais NÃO estão disponíveis hoje:\n{linhas}\n"
            "Mencione brevemente no primeiro parágrafo."
        )
    else:
        aviso = ""

    resposta = client.models.generate_content(
        model=MODEL,
        contents=_PROMPT_RESUMO.format(
            n_canais=len(transcricoes),
            data=data_ref,
            canais_presentes=", ".join(c.upper() for c in transcricoes),
            aviso_ausentes=aviso,
            transcricoes=blocos,
        ),
        config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=1024),
    )
    return resposta.text.strip()
