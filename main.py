import os
import re
import json
import subprocess
import shutil
import smtplib
import sys
from datetime import datetime, date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google import genai
from google.genai import types
from youtube_transcript_api import YouTubeTranscriptApi

# ================================================================
# Configuração via variáveis de ambiente
# ================================================================
GEMINI_API_KEY  = os.environ['GEMINI_API_KEY']
EMAIL_REMETENTE = os.environ['EMAIL_REMETENTE']
EMAIL_SENHA_APP = os.environ['EMAIL_SENHA_APP']

with open('config.json', encoding='utf-8') as f:
    CONFIG = json.load(f)
DESTINATARIOS = CONFIG['destinatarios']

MODELO_PRINCIPAL = 'gemini-3.1-flash-lite'
client    = genai.Client(api_key=GEMINI_API_KEY)
_ytdlp_bin = shutil.which('yt-dlp')
YTDLP_CMD  = [_ytdlp_bin] if _ytdlp_bin else [sys.executable, '-m', 'yt_dlp']

# ================================================================
# Canais validados
# ================================================================
CANAIS_MORNING_CALL = {
    'btg':       {'url': 'https://www.youtube.com/@BTGPactual/streams',         'keywords': ['morning call', 'btg pactual']},
    'genial':    {'url': 'https://www.youtube.com/@genialinvestimentos/streams', 'keywords': ['resumo da manhã', 'morning call genial']},
    'investing': {'url': 'https://www.youtube.com/@investingcombr/streams',     'keywords': ['morning call']},
    'xp':        {'url': 'https://www.youtube.com/@XP_Oficial/streams',         'keywords': ['morning call']},
}

# ================================================================
# Funções de data
# ================================================================
def ultimo_dia_util() -> date:
    agora = datetime.now()
    hoje  = agora.date()
    if hoje.weekday() < 5 and agora.hour >= 10:
        return hoje
    d = hoje - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

# ================================================================
# Busca e seleção de vídeos
# ================================================================
PROMPT_SELECAO = """
Você é um assistente especializado em conteúdo financeiro do YouTube brasileiro.

Sua tarefa é identificar qual vídeo da lista abaixo é o MORNING CALL do dia {data}.

O morning call é um programa jornalístico de mercado transmitido toda manhã antes ou
durante a abertura do pregão. Cada canal pode usar nomes diferentes:
- "Morning Call", "Resumo da Manhã", "Abertura de Mercado", "Panorama do Dia"
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


def buscar_video_canal(nome_canal: str, config: dict,
                        dia_alvo: date, max_busca: int = 20) -> tuple:
    dia_str = dia_alvo.strftime('%Y%m%d')

    cmd = YTDLP_CMD + [
        '--flat-playlist', '--playlist-end', str(max_busca),
        '--print', '%(id)s\t%(title)s\t%(duration)s',
        '--no-warnings', config['url']
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if not r.stdout.strip():
        return None, 'canal inacessível ou sem vídeos'

    videos = []
    for linha in r.stdout.strip().split('\n'):
        partes = linha.split('\t')
        if len(partes) < 2:
            continue
        try:
            duracao = int(float(partes[2])) if len(partes) > 2 else 0
        except Exception:
            duracao = 0
        videos.append({
            'id':          partes[0].strip(),
            'titulo':      partes[1].strip(),
            'data':        '',
            'duracao_seg': duracao,
            'url':         f'https://youtube.com/watch?v={partes[0].strip()}'
        })

    for v in videos:
        try:
            r2 = subprocess.run(
                YTDLP_CMD + ['--no-warnings', '--skip-download',
                             '--print', '%(release_date)s\t%(upload_date)s', v['url']],
                capture_output=True, text=True, timeout=30
            )
            partes_data = r2.stdout.strip().split('\t')
            release = partes_data[0].strip() if len(partes_data) > 0 else ''
            upload  = partes_data[1].strip() if len(partes_data) > 1 else ''
            if release and release not in ('NA', 'None', ''):
                v['data'] = release
            elif upload and upload not in ('NA', 'None', ''):
                v['data'] = upload
        except Exception:
            v['data'] = ''

    videos_do_dia = [v for v in videos if v['data'] == dia_str]

    if not videos_do_dia:
        ultimo     = max((v for v in videos if v['data']), key=lambda x: x['data'], default=None)
        ultima_data = ultimo['data'] if ultimo else 'desconhecida'
        return None, f'nenhum vídeo publicado em {dia_alvo.strftime("%d/%m/%Y")} (último: {ultima_data})'

    print(f'   📋 [{nome_canal}] {len(videos_do_dia)} vídeo(s) do dia — IA selecionando...')

    videos_slim = [{'id': v['id'], 'titulo': v['titulo'],
                    'duracao': f'{v["duracao_seg"]//60}min', 'data': v['data']}
                   for v in videos_do_dia]

    prompt = PROMPT_SELECAO.format(
        data=dia_alvo.strftime('%d/%m/%Y'),
        data_yyyymmdd=dia_str,
        videos_json=json.dumps(videos_slim, ensure_ascii=False, indent=2)
    )

    resposta = client.models.generate_content(
        model=MODELO_PRINCIPAL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=512,
            response_mime_type='application/json'
        )
    )

    texto     = re.sub(r'^```json\s*|\s*```$', '', resposta.text.strip(), flags=re.MULTILINE).strip()
    resultado = json.loads(texto)

    escolhido_id = resultado.get('escolhido', {}).get('id')
    motivo_ia    = resultado.get('escolhido', {}).get('motivo', '')

    if not escolhido_id or escolhido_id in ('null', None):
        return None, 'IA não identificou morning call entre os vídeos do dia'

    video = next((v for v in videos_do_dia if v['id'] == escolhido_id), None)
    if not video:
        return None, f'IA escolheu id {escolhido_id} mas não encontrado na lista'

    if video['duracao_seg'] < 300:
        return None, f'vídeo selecionado muito curto ({video["duracao_seg"]}s) — provável live em andamento'

    print(f'   ✅ [{nome_canal}] {video["titulo"][:55]} ({video["duracao_seg"]//60}min)')
    print(f'      Motivo IA: {motivo_ia}')
    return video, None


# ================================================================
# Transcrição
# ================================================================
def obter_transcricao(url_ou_id: str) -> dict:
    video_id = (url_ou_id if len(url_ou_id) == 11
                else re.search(r'(?:v=|youtu\.be/)([\w-]{11})', url_ou_id).group(1))

    ytt   = YouTubeTranscriptApi()
    lista = ytt.list(video_id)

    transcript = None
    for metodo in [
        lambda: lista.find_manually_created_transcript(['pt', 'pt-BR', 'en']),
        lambda: lista.find_generated_transcript(['pt', 'pt-BR', 'en']),
        lambda: next(iter(lista))
    ]:
        try:
            transcript = metodo()
            break
        except Exception:
            continue

    if transcript is None:
        raise RuntimeError('nenhuma transcrição encontrada para este vídeo')

    segmentos = transcript.fetch()
    texto     = ' '.join(s.text for s in segmentos)
    duracao   = int(segmentos[-1].start + (segmentos[-1].duration or 0))

    return {'video_id': video_id, 'texto_completo': texto, 'duracao_segundos': duracao}


# ================================================================
# Resumo com Gemini
# ================================================================
PROMPT_RESUMO = """
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


def gerar_resumo(transcricoes_por_canal: dict, canais_ausentes: dict, data_ref: str) -> str:
    bloco = ''
    for canal, texto in transcricoes_por_canal.items():
        texto_trim = texto[:40_000] + '...[truncado]' if len(texto) > 40_000 else texto
        bloco += f'\n[{canal.upper()}]\n{texto_trim}\n'

    if canais_ausentes:
        linhas = '\n'.join(f'- {c.upper()}: {m}' for c, m in canais_ausentes.items())
        aviso  = (f'ATENÇÃO: Os seguintes canais NÃO estão disponíveis hoje:\n{linhas}\n'
                  f'Mencione brevemente no primeiro parágrafo.')
    else:
        aviso = ''

    prompt = PROMPT_RESUMO.format(
        n_canais=len(transcricoes_por_canal),
        data=data_ref,
        canais_presentes=', '.join(c.upper() for c in transcricoes_por_canal.keys()),
        aviso_ausentes=aviso,
        transcricoes=bloco
    )

    resposta = client.models.generate_content(
        model=MODELO_PRINCIPAL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=1024)
    )
    return resposta.text.strip()


# ================================================================
# Email
# ================================================================
def montar_html(resumo: str, data_ref: str, canais_usados: list,
                 canais_ausentes: dict, videos_info: list) -> str:
    paragrafos = ''.join(
        f'<p style="margin:0 0 14px 0;">{p.strip()}</p>'
        for p in resumo.split('\n') if p.strip()
    )
    fontes = ''.join(
        f'<li><a href="{v["url"]}" style="color:#1a73e8;">'
        f'[{v["canal"].upper()}] {v["titulo"][:70]}</a></li>'
        for v in videos_info
    )
    bloco_ausentes = ''
    if canais_ausentes:
        itens = ''.join(f'<li><b>{c.upper()}</b>: {m}</li>' for c, m in canais_ausentes.items())
        bloco_ausentes = f"""
        <div style="background:#fff8e1;border-left:4px solid #f9a825;
                    padding:12px 16px;margin-bottom:16px;border-radius:4px;">
          <p style="margin:0 0 6px 0;font-size:13px;font-weight:bold;color:#f57f17;">
            ⚠️ Canais ausentes hoje</p>
          <ul style="margin:0;padding-left:16px;font-size:12px;color:#555;">{itens}</ul>
        </div>"""

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222;">
      <div style="background:#1a1a2e;padding:20px 28px;border-radius:8px 8px 0 0;">
        <h2 style="color:#fff;margin:0;font-size:18px;">📊 Morning Call Digest</h2>
        <p style="color:#aaa;margin:4px 0 0 0;font-size:13px;">
          {data_ref} &nbsp;·&nbsp; {', '.join(c.upper() for c in canais_usados)}</p>
      </div>
      <div style="background:#f9f9f9;padding:24px 28px;border:1px solid #e0e0e0;border-top:none;">
        {bloco_ausentes}{paragrafos}
      </div>
      <div style="padding:16px 28px;border:1px solid #e0e0e0;border-top:none;background:#fff;">
        <p style="font-size:12px;color:#888;margin:0 0 8px 0;">Fontes:</p>
        <ul style="font-size:12px;color:#555;margin:0;padding-left:18px;">{fontes}</ul>
      </div>
      <p style="font-size:11px;color:#bbb;text-align:center;margin-top:12px;">
        Gerado automaticamente · {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </body></html>"""


def enviar_emails(resumo: str, data_ref: str, canais_usados: list,
                   canais_ausentes: dict, videos_info: list):
    n_ausentes = len(canais_ausentes)
    sufixo     = f' — ⚠️ {n_ausentes} canal(is) ausente(s)' if n_ausentes else ''
    assunto    = f'📊 Morning Call Digest — {data_ref}{sufixo}'
    html       = montar_html(resumo, data_ref, canais_usados, canais_ausentes, videos_info)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = assunto
    msg['From']    = EMAIL_REMETENTE
    msg['To']      = ', '.join(DESTINATARIOS)
    msg.attach(MIMEText(resumo, 'plain', 'utf-8'))
    msg.attach(MIMEText(html,   'html',  'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_REMETENTE, EMAIL_SENHA_APP)
        smtp.sendmail(EMAIL_REMETENTE, DESTINATARIOS, msg.as_string())
    print(f'✅ Email enviado para: {", ".join(DESTINATARIOS)}')


def enviar_email_sem_digest(data_ref: str, canais_ausentes: dict):
    itens = ''.join(f'<li><b>{c.upper()}</b>: {m}</li>' for c, m in canais_ausentes.items())
    html  = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222;">
      <div style="background:#1a1a2e;padding:20px 28px;border-radius:8px 8px 0 0;">
        <h2 style="color:#fff;margin:0;font-size:18px;">📊 Morning Call Digest</h2>
        <p style="color:#aaa;margin:4px 0 0 0;font-size:13px;">{data_ref}</p>
      </div>
      <div style="background:#f9f9f9;padding:24px 28px;border:1px solid #e0e0e0;border-top:none;">
        <div style="background:#ffebee;border-left:4px solid #c62828;
                    padding:12px 16px;border-radius:4px;">
          <p style="margin:0 0 8px 0;font-weight:bold;color:#b71c1c;">
            ❌ Nenhum morning call disponível para {data_ref}</p>
          <ul style="font-size:13px;color:#555;margin:0;padding-left:16px;">{itens}</ul>
        </div>
      </div>
    </body></html>"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'📊 Morning Call Digest — {data_ref} — ❌ Sem conteúdo'
    msg['From']    = EMAIL_REMETENTE
    msg['To']      = ', '.join(DESTINATARIOS)
    msg.attach(MIMEText(f'Nenhum morning call disponível para {data_ref}.', 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_REMETENTE, EMAIL_SENHA_APP)
        smtp.sendmail(EMAIL_REMETENTE, DESTINATARIOS, msg.as_string())
    print('✅ Email de aviso enviado')


# ================================================================
# Verificação de bloqueio de IP
# ================================================================
def verificar_ip_bloqueado() -> bool:
    """Testa uma transcrição rápida antes de começar o pipeline.
    Retorna True se o IP estiver bloqueado."""
    VIDEO_TESTE = 'jNQXAC9IVRw'  # "Me at the zoo" — primeiro vídeo do YouTube, sempre disponível
    try:
        ytt = YouTubeTranscriptApi()
        ytt.list(VIDEO_TESTE)
        return False
    except Exception as e:
        msg = str(e).lower()
        if 'blocked' in msg or 'bot' in msg or 'ip' in msg:
            return True
        return False


def enviar_email_ip_bloqueado(data_ref: str):
    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222;">
      <div style="background:#1a1a2e;padding:20px 28px;border-radius:8px 8px 0 0;">
        <h2 style="color:#fff;margin:0;font-size:18px;">📊 Morning Call Digest</h2>
        <p style="color:#aaa;margin:4px 0 0 0;font-size:13px;">{data_ref}</p>
      </div>
      <div style="background:#f9f9f9;padding:24px 28px;border:1px solid #e0e0e0;border-top:none;">
        <div style="background:#fff3e0;border-left:4px solid #e65100;
                    padding:12px 16px;border-radius:4px;">
          <p style="margin:0 0 8px 0;font-weight:bold;color:#bf360c;">
            🚫 IP bloqueado pelo YouTube</p>
          <p style="font-size:13px;color:#555;margin:0;">
            O script detectou bloqueio antes de iniciar e abortou para não forçar o IP.
            O bloqueio é temporário — tente rodar manualmente mais tarde.</p>
        </div>
      </div>
    </body></html>"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'📊 Morning Call Digest — {data_ref} — 🚫 IP bloqueado'
    msg['From']    = EMAIL_REMETENTE
    msg['To']      = ', '.join(DESTINATARIOS)
    msg.attach(MIMEText(f'IP bloqueado pelo YouTube em {data_ref}. Tente manualmente mais tarde.', 'plain', 'utf-8'))
    msg.attach(MIMEText(html, 'html', 'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_REMETENTE, EMAIL_SENHA_APP)
        smtp.sendmail(EMAIL_REMETENTE, DESTINATARIOS, msg.as_string())
    print('✅ Email de aviso de IP bloqueado enviado')


# ================================================================
# Pipeline principal
# ================================================================
def main():
    dia      = ultimo_dia_util()
    data_ref = dia.strftime('%d/%m/%Y')
    print(f'🗓️  Digest de: {data_ref}\n')

    print('🔍 Verificando bloqueio de IP...')
    if verificar_ip_bloqueado():
        print('🚫 IP bloqueado — abortando para não forçar. Email de aviso enviado.')
        enviar_email_ip_bloqueado(data_ref)
        return
    print('✅ IP liberado — iniciando coleta\n')

    transcricoes_por_canal = {}
    canais_ausentes        = {}
    videos_info            = []

    for nome, config in CANAIS_MORNING_CALL.items():
        print(f'📡 [{nome}]')
        try:
            video, motivo = buscar_video_canal(nome, config, dia_alvo=dia)
            if not video:
                canais_ausentes[nome] = motivo
                print(f'   ⚠️  Ausente: {motivo}\n')
                continue

            transcricao = obter_transcricao(video['url'])
            transcricoes_por_canal[nome] = transcricao['texto_completo']
            videos_info.append({'canal': nome, 'titulo': video['titulo'], 'url': video['url']})
            print(f'   ✅ OK | {transcricao["duracao_segundos"]//60}min | '
                  f'{len(transcricao["texto_completo"]):,} chars\n')

        except Exception as e:
            motivo = str(e)[:120]
            canais_ausentes[nome] = f'erro técnico: {motivo}'
            print(f'   ❌ Erro: {motivo}\n')

    coletados = len(transcricoes_por_canal)
    total     = len(CANAIS_MORNING_CALL)
    print(f'📊 {coletados}/{total} canais coletados\n')

    if coletados == 0:
        print('❌ Nenhum canal disponível — enviando email de aviso')
        enviar_email_sem_digest(data_ref, canais_ausentes)
        return

    resumo = gerar_resumo(transcricoes_por_canal, canais_ausentes, data_ref)
    print(f'\n{"="*60}\n{resumo}\n{"="*60}\n')

    enviar_emails(resumo, data_ref,
                  list(transcricoes_por_canal.keys()),
                  canais_ausentes,
                  videos_info)


if __name__ == '__main__':
    main()
