import time
from datetime import date, datetime, timedelta

from config import CHANNELS, TRANSCRIPT_RETRIES, TRANSCRIPT_RETRY_WAIT
from emailer import enviar_aviso_ip_bloqueado, enviar_aviso_sem_digest, enviar_digest
from prices import obter_precos
from summarizer import gerar_resumo
from youtube import buscar_video_canal, obter_transcricao, sleep_humano, verificar_ip_bloqueado


def ultimo_dia_util() -> date:
    agora = datetime.now()
    hoje  = agora.date()
    if hoje.weekday() < 5 and agora.hour >= 9:
        return hoje
    d = hoje - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def main() -> None:
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

            transcricao = None
            ultimo_erro = None
            for tentativa in range(1, TRANSCRIPT_RETRIES + 1):
                try:
                    transcricao = obter_transcricao(video["url"])
                    break
                except Exception as e:
                    ultimo_erro = e
                    if tentativa < TRANSCRIPT_RETRIES:
                        print(f"   ⏳ Transcrição indisponível — aguardando 10min (tentativa {tentativa}/{TRANSCRIPT_RETRIES})...")
                        time.sleep(TRANSCRIPT_RETRY_WAIT)

            if transcricao is None:
                raise ultimo_erro

            transcricoes[canal] = transcricao["texto_completo"]
            videos_info.append({"canal": canal, "titulo": video["titulo"], "url": video["url"]})
            print(f'   ✅ OK | {transcricao["duracao_segundos"] // 60}min | {len(transcricao["texto_completo"]):,} chars\n')

        except Exception as e:
            ausentes[canal] = f"erro técnico: {str(e)[:120]}"
            print(f"   ❌ Erro: {str(e)[:120]}\n")

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
        print(f"⚠️  Falha ao buscar preços: {str(e)[:80]}")
        precos = []

    enviar_digest(resumo, data_ref, list(transcricoes.keys()), ausentes, videos_info, precos)


if __name__ == "__main__":
    main()
