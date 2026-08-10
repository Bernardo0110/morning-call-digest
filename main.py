import ctypes
import time
import traceback
from datetime import date, datetime, timedelta

from config import CHANNELS, TRANSCRIPT_RETRIES, TRANSCRIPT_RETRY_WAIT
from emailer import enviar_aviso_ip_bloqueado, enviar_aviso_sem_digest, enviar_digest
from prices import obter_precos
from summarizer import gerar_resumo
from youtube import buscar_video_canal, obter_transcricao, sleep_humano, verificar_ip_bloqueado

# Impede o Windows de suspender o PC por ociosidade durante a execução.
# WakeToRun acorda o PC para a tarefa, mas NÃO o mantém acordado: sem atividade
# de usuário, o timer de suspensão dispara e congela o processo no meio (foi o
# que aconteceu em 03/06 — o run só terminou quando o PC foi religado à mão).
# ES_SYSTEM_REQUIRED segura o sistema acordado; a suspensão intencional do
# run.ps1 ao final continua funcionando porque é forçada.
_ES_CONTINUOUS      = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001


def _impedir_suspensao() -> None:
    try:
        fn = ctypes.windll.kernel32.SetThreadExecutionState
        fn.argtypes = [ctypes.c_uint]
        fn.restype  = ctypes.c_uint
        if fn(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED):
            print("🔌 Suspensão por ociosidade bloqueada durante a execução")
        else:
            print("⚠️  SetThreadExecutionState retornou 0 — suspensão não bloqueada")
    except Exception as e:
        print(f"⚠️  Não foi possível bloquear a suspensão: {e}")


def _permitir_suspensao() -> None:
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    except Exception:
        pass


def ultimo_dia_util() -> date:
    agora = datetime.now()
    hoje  = agora.date()
    if hoje.weekday() < 5 and agora.hour >= 9:
        return hoje
    d = hoje - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _executar() -> None:
    dia      = ultimo_dia_util()
    data_ref = dia.strftime("%d/%m/%Y")
    print(f"🗓️  Digest de: {data_ref}\n")

    print("🔍 Verificando bloqueio de IP...")
    if verificar_ip_bloqueado():
        print("🚫 IP bloqueado — abortando. Email de aviso enviado.")
        enviar_aviso_ip_bloqueado(data_ref)
        return
    print("✅ IP liberado — iniciando coleta\n")

    transcricoes: dict[str, str] = {}
    ausentes:     dict[str, str] = {}
    videos_info:  list[dict]     = []
    primeiro = True

    for canal, cfg in CHANNELS.items():
        if not primeiro:
            sleep_humano(12, 25)
        primeiro = False

        print(f"📡 [{canal}]")
        try:
            video, motivo = buscar_video_canal(canal, cfg["url"], dia_alvo=dia, min_secs=cfg["min_secs"])
            if not video:
                ausentes[canal] = motivo
                print(f"   ⚠️  Ausente: {motivo}\n")
                continue

            sleep_humano(5, 12)

            retries = cfg.get("retries", TRANSCRIPT_RETRIES)
            transcricao = None
            ultimo_erro = None
            for tentativa in range(1, retries + 1):
                try:
                    transcricao = obter_transcricao(video["url"])
                    break
                except Exception as e:
                    ultimo_erro = e
                    if tentativa < retries:
                        print(f"   ⏳ Transcrição indisponível — aguardando 10min (tentativa {tentativa}/{retries})...")
                        time.sleep(TRANSCRIPT_RETRY_WAIT)

            if transcricao is None:
                raise ultimo_erro

            transcricoes[canal] = transcricao["texto_completo"]
            videos_info.append({"canal": canal, "titulo": video["titulo"], "url": video["url"]})
            print(f'   ✅ OK | {transcricao["duracao_segundos"] // 60}min | {len(transcricao["texto_completo"]):,} chars\n')

        except Exception as e:
            # No email (via `ausentes`) o texto fica curto e legível. No log,
            # a mensagem completa + traceback ficam sem corte — é o que
            # permite diagnosticar a causa real depois (mensagens truncadas
            # em 80-120 chars já esconderam informação importante no passado).
            ausentes[canal] = f"erro técnico: {str(e)[:200]}"
            print(f"   ❌ Erro: {e}")
            print(f"   {traceback.format_exc()}\n")

    print(f"📊 {len(transcricoes)}/{len(CHANNELS)} canais coletados\n")

    if not transcricoes:
        print("❌ Nenhum canal disponível — enviando email de aviso")
        enviar_aviso_sem_digest(data_ref, ausentes)
        return

    resumo = gerar_resumo(transcricoes, ausentes, data_ref)
    print(f'\n{"=" * 60}\n{resumo}\n{"=" * 60}\n')

    print("📈 Buscando preços de mercado...")
    try:
        precos = obter_precos()
    except Exception as e:
        print(f"⚠️  Falha ao buscar preços: {e}")
        print(f"   {traceback.format_exc()}")
        precos = []

    enviar_digest(resumo, data_ref, list(transcricoes.keys()), ausentes, videos_info, precos)


def main() -> None:
    _impedir_suspensao()
    try:
        _executar()
    finally:
        _permitir_suspensao()


if __name__ == "__main__":
    main()
