import json
import os
import shutil
import sys
from pathlib import Path

from google import genai

GEMINI_KEY     = os.environ["GEMINI_API_KEY"]
EMAIL_FROM     = os.environ["EMAIL_REMETENTE"]
EMAIL_PASSWORD = os.environ["EMAIL_SENHA_APP"]

with open(Path(__file__).parent / "config.json", encoding="utf-8") as _f:
    _cfg = json.load(_f)

TEST_MODE  = os.environ.get("TEST_MODE", "").strip().lower() == "true"
RECIPIENTS = [EMAIL_FROM] if TEST_MODE else _cfg["destinatarios"]

if TEST_MODE:
    print("⚠️  TEST_MODE active — email enviado apenas para o remetente")

TRANSCRIPT_RETRIES    = 3
TRANSCRIPT_RETRY_WAIT = 10 * 60   # segundos entre tentativas
MODEL                 = "gemini-3.1-flash-lite"
MIN_VIDEO_SECS        = 300        # abaixo disso = live provavelmente em andamento
MAX_TRANSCRIPT_CHARS  = 40_000
IP_CHECK_VIDEO        = "jNQXAC9IVRw"  # "Me at the zoo" — sempre tem transcrição

# Bloqueios de IP costumam ser rate-limit temporário, não um ban permanente.
# Antes de desistir do dia inteiro, o check é refeito depois de uma espera.
IP_CHECK_RETRIES    = 2
IP_CHECK_RETRY_WAIT = 5 * 60   # segundos entre tentativas do check de IP

# cookies.txt (formato Netscape, exportado de uma conta Google dedicada logada
# no navegador) é opcional. Se existir, autentica as requisições ao YouTube —
# tráfego autenticado é tratado de forma bem menos suspeita pelo anti-bot do
# que tráfego anônimo. Ausência do arquivo não quebra nada, só volta a rodar
# anônimo. Nunca commitar (mesma categoria de secrets.env).
COOKIES_FILE = Path(__file__).parent / "cookies.txt"

client = genai.Client(api_key=GEMINI_KEY)

_ytdlp = shutil.which("yt-dlp")
YTDLP  = [_ytdlp] if _ytdlp else [sys.executable, "-m", "yt_dlp"]
if COOKIES_FILE.exists():
    YTDLP = YTDLP + ["--cookies", str(COOKIES_FILE)]

# Cada canal aponta para a aba de vídeos/lives e define a duração mínima do
# vídeo selecionado. min_secs filtra lives em andamento (duração ~0) e shorts.
# PicPay (Diário Econômico) publica episódios curtos (~5min) em /videos, por
# isso usa um mínimo menor; os demais são lives longas em /streams.
#
# "retries" (opcional, default TRANSCRIPT_RETRIES): o Investing usa 1 (sem
# retry) porque o YouTube demora ~13h para finalizar o processamento da live
# dele (confirmado via release_timestamp/timestamp em 09/08/2026 — outros
# canais finalizam em ~35min). Nenhum retry dentro da janela de execução das
# 10:30 resolve isso, então esperar 10/20min a mais só atrasa o digest à toa.
# O canal deve mesmo ficar de fora do digest na maioria dos dias — decisão
# aceita, não é bug a corrigir.
CHANNELS: dict[str, dict] = {
    "btg":       {"url": "https://www.youtube.com/@BTGPactual/streams",            "min_secs": MIN_VIDEO_SECS},
    "genial":    {"url": "https://www.youtube.com/@genialinvestimentos/streams",   "min_secs": MIN_VIDEO_SECS},
    "investing": {"url": "https://www.youtube.com/@investingcombr/streams",        "min_secs": MIN_VIDEO_SECS, "retries": 1},
    "xp":        {"url": "https://www.youtube.com/@XP_Oficial/streams",            "min_secs": MIN_VIDEO_SECS},
    "picpay":    {"url": "https://www.youtube.com/@PodcastDiarioEconomico/videos", "min_secs": 120},
}
