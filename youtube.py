import http.cookiejar
import json
import random
import re
import subprocess
import time
from datetime import date

import requests
from google.genai import types
from youtube_transcript_api import RequestBlocked, YouTubeTranscriptApi

from config import (
    COOKIES_FILE, IP_CHECK_VIDEO, MAX_TRANSCRIPT_CHARS, MIN_VIDEO_SECS,
    MODEL, YTDLP, client,
)

_PROMPT_SELECAO = """
Você é um assistente especializado em conteúdo financeiro do YouTube brasileiro.

Sua tarefa é identificar qual vídeo da lista abaixo é o MORNING CALL do dia {data}.

O morning call é um programa jornalístico de mercado transmitido toda manhã antes ou
durante a abertura do pregão. Cada canal pode usar nomes diferentes:
- "Morning Call", "Resumo da Manhã", "Abertura de Mercado", "Panorama do Dia"
- "Diário Econômico" / "Economic Daily" (podcast diário de economia; o título pode vir traduzido para inglês)
- Título com a data do dia + assuntos do mercado (ex: "22/05 Petróleo cai 5%...")

NÃO é morning call:
- Day Trade ao vivo (operações em tempo real, geralmente +2h)
- Fechamento de mercado
- Análise de ações específicas sem contexto macro do dia
- Tutoriais ou conteúdo educacional
- Entrevistas temáticas sem foco no panorama do dia

IMPORTANTE:
- O vídeo DEVE ser do dia {data} (formato YYYYMMDD = {data_yyyymmdd})
- Se nenhum vídeo do dia for morning call, retorne null no id
- Escolha apenas UM vídeo

Retorne SOMENTE JSON puro:
{{
  "escolhido": {{
    "id": "video_id ou null",
    "titulo": "título ou null",
    "motivo": "1 frase explicando a escolha"
  }},
  "descartados": [
    {{"id": "video_id", "motivo": "motivo do descarte"}}
  ]
}}

VÍDEOS DISPONÍVEIS:
{videos_json}
"""


def sleep_humano(minimo: float, maximo: float) -> None:
    time.sleep(random.uniform(minimo, maximo))


_sessao_carregada = False
_sessao: requests.Session | None = None


def _obter_sessao() -> requests.Session | None:
    """Sessão HTTP com cookies de cookies.txt, se o arquivo existir.
    Carregada uma única vez e reaproveitada em todas as chamadas à
    youtube_transcript_api (que não expõe mais um parâmetro de cookie_path
    próprio — precisa ser um requests.Session já autenticado)."""
    global _sessao, _sessao_carregada
    if not _sessao_carregada:
        _sessao_carregada = True
        if COOKIES_FILE.exists():
            try:
                jar = http.cookiejar.MozillaCookieJar(str(COOKIES_FILE))
                jar.load(ignore_discard=True, ignore_expires=True)
                sessao = requests.Session()
                sessao.cookies = jar
                _sessao = sessao
                print("🍪 cookies.txt carregado — requests autenticados")
            except Exception as e:
                print(f"⚠️  Falha ao carregar cookies.txt ({e}) — seguindo sem autenticação")
    return _sessao


def verificar_ip_bloqueado() -> bool:
    try:
        YouTubeTranscriptApi(http_client=_obter_sessao()).list(IP_CHECK_VIDEO)
        return False
    except RequestBlocked as e:
        # RequestBlocked (e sua subclasse IpBlocked) é o sinal específico da
        # lib pra bloqueio real. Logar a causa completa aqui é o que permite
        # diferenciar bloqueio de verdade de qualquer outro erro no log.
        print(f"   🚫 Causa reportada pela lib: {e}")
        return True
    except Exception as e:
        # Qualquer outro erro (timeout, DNS, vídeo de check indisponível etc.)
        # não é bloqueio de IP — antes um match de substring solto (`"ip" in
        # msg`) classificava isso como bloqueio e abortava o dia à toa.
        print(f"   ⚠️  Erro no check de IP, não classificado como bloqueio: {e}")
        return False


def buscar_video_canal(
    canal: str,
    url: str,
    dia_alvo: date,
    max_busca: int = 8,
    min_secs: int = MIN_VIDEO_SECS,
) -> tuple[dict | None, str | None]:
    dia_str = dia_alvo.strftime("%Y%m%d")

    resultado = subprocess.run(
        YTDLP + [
            "--flat-playlist", "--playlist-end", str(max_busca),
            "--print", "%(id)s\t%(title)s\t%(duration)s",
            "--no-warnings", url,
        ],
        capture_output=True, text=True, timeout=60,
    )

    if not resultado.stdout.strip():
        return None, "canal inacessível ou sem vídeos"

    videos: list[dict] = []
    for linha in resultado.stdout.strip().split("\n"):
        partes = linha.split("\t")
        if len(partes) < 2:
            continue
        try:
            duracao = int(float(partes[2])) if len(partes) > 2 else 0
        except (ValueError, IndexError):
            duracao = 0
        video_id = partes[0].strip()
        videos.append({
            "id":          video_id,
            "titulo":      partes[1].strip(),
            "data":        "",
            "duracao_seg": duracao,
            "url":         f"https://youtube.com/watch?v={video_id}",
        })

    for video in videos:
        sleep_humano(3, 8)
        try:
            res = subprocess.run(
                YTDLP + [
                    "--no-warnings", "--skip-download",
                    "--print", "%(release_date)s\t%(upload_date)s", video["url"],
                ],
                capture_output=True, text=True, timeout=30,
            )
            partes_data = res.stdout.strip().split("\t")
            release = partes_data[0].strip() if len(partes_data) > 0 else ""
            upload  = partes_data[1].strip() if len(partes_data) > 1 else ""
            if release and release not in ("NA", "None", ""):
                video["data"] = release
            elif upload and upload not in ("NA", "None", ""):
                video["data"] = upload
        except Exception:
            pass

    videos_do_dia = [v for v in videos if v["data"] == dia_str]

    if not videos_do_dia:
        ultimo = max(
            (v for v in videos if v["data"]),
            key=lambda v: v["data"],
            default=None,
        )
        ultima_data = ultimo["data"] if ultimo else "desconhecida"
        return None, f'nenhum vídeo publicado em {dia_alvo.strftime("%d/%m/%Y")} (último: {ultima_data})'

    print(f"   📋 [{canal}] {len(videos_do_dia)} vídeo(s) do dia — IA selecionando...")

    videos_slim = [
        {
            "id":      v["id"],
            "titulo":  v["titulo"],
            "duracao": f'{v["duracao_seg"] // 60}min',
            "data":    v["data"],
        }
        for v in videos_do_dia
    ]

    resposta = client.models.generate_content(
        model=MODEL,
        contents=_PROMPT_SELECAO.format(
            data=dia_alvo.strftime("%d/%m/%Y"),
            data_yyyymmdd=dia_str,
            videos_json=json.dumps(videos_slim, ensure_ascii=False, indent=2),
        ),
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=512,
            response_mime_type="application/json",
        ),
    )

    texto   = re.sub(r"^```json\s*|\s*```$", "", resposta.text.strip(), flags=re.MULTILINE)
    selecao = json.loads(texto)

    escolhido_id = selecao.get("escolhido", {}).get("id")
    motivo_ia    = selecao.get("escolhido", {}).get("motivo", "")

    if not escolhido_id or escolhido_id in ("null", None):
        return None, "IA não identificou morning call entre os vídeos do dia"

    video = next((v for v in videos_do_dia if v["id"] == escolhido_id), None)
    if not video:
        return None, f"IA escolheu id {escolhido_id} mas não encontrado na lista"

    if video["duracao_seg"] < min_secs:
        return None, f'vídeo selecionado muito curto ({video["duracao_seg"]}s) — provável live em andamento'

    print(f'   ✅ [{canal}] {video["titulo"][:55]} ({video["duracao_seg"] // 60}min)')
    print(f"      Motivo IA: {motivo_ia}")
    return video, None


def obter_transcricao(url_ou_id: str) -> dict:
    video_id = (
        url_ou_id
        if len(url_ou_id) == 11
        else re.search(r"(?:v=|youtu\.be/)([\w-]{11})", url_ou_id).group(1)
    )

    lista = YouTubeTranscriptApi(http_client=_obter_sessao()).list(video_id)

    transcript = None
    for tentativa in [
        lambda: lista.find_manually_created_transcript(["pt", "pt-BR", "en"]),
        lambda: lista.find_generated_transcript(["pt", "pt-BR", "en"]),
        lambda: next(iter(lista)),
    ]:
        try:
            transcript = tentativa()
            break
        except Exception:
            continue

    if transcript is None:
        raise RuntimeError("nenhuma transcrição encontrada para este vídeo")

    segmentos = transcript.fetch()
    return {
        "video_id":         video_id,
        "texto_completo":   " ".join(s.text for s in segmentos),
        "duracao_segundos": int(segmentos[-1].start + (segmentos[-1].duration or 0)),
    }
