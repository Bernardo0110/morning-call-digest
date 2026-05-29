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

client = genai.Client(api_key=GEMINI_KEY)

_ytdlp = shutil.which("yt-dlp")
YTDLP  = [_ytdlp] if _ytdlp else [sys.executable, "-m", "yt_dlp"]

CHANNELS: dict[str, str] = {
    "btg":       "https://www.youtube.com/@BTGPactual/streams",
    "genial":    "https://www.youtube.com/@genialinvestimentos/streams",
    "investing": "https://www.youtube.com/@investingcombr/streams",
    "xp":        "https://www.youtube.com/@XP_Oficial/streams",
}
