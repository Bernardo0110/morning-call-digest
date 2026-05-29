import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import EMAIL_FROM, EMAIL_PASSWORD, RECIPIENTS


def _cabecalho(data_ref: str, canais: list[str] | None = None) -> str:
    subtitulo = (
        f"{data_ref} &nbsp;·&nbsp; {', '.join(c.upper() for c in canais)}"
        if canais else data_ref
    )
    return (
        '<div style="background:#1a1a2e;padding:20px 28px;border-radius:8px 8px 0 0;">'
        '<h2 style="color:#fff;margin:0;font-size:18px;">📊 Morning Call Digest</h2>'
        f'<p style="color:#aaa;margin:4px 0 0 0;font-size:13px;">{subtitulo}</p>'
        "</div>"
    )


def _enviar(assunto: str, texto_plain: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"]    = EMAIL_FROM
    msg["To"]      = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(texto_plain, "plain", "utf-8"))
    msg.attach(MIMEText(html,        "html",  "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_FROM, EMAIL_PASSWORD)
        smtp.sendmail(EMAIL_FROM, RECIPIENTS, msg.as_string())
    print(f"✅ Email enviado para: {', '.join(RECIPIENTS)}")


def enviar_digest(
    resumo: str,
    data_ref: str,
    canais_usados: list[str],
    ausentes: dict[str, str],
    videos: list[dict],
) -> None:
    sufixo  = f" — ⚠️ {len(ausentes)} canal(is) ausente(s)" if ausentes else ""
    assunto = f"📊 Morning Call Digest — {data_ref}{sufixo}"

    paragrafos = "".join(
        f'<p style="margin:0 0 14px 0;">{p.strip()}</p>'
        for p in resumo.split("\n") if p.strip()
    )
    fontes = "".join(
        f'<li><a href="{v["url"]}" style="color:#1a73e8;">'
        f'[{v["canal"].upper()}] {v["titulo"][:70]}</a></li>'
        for v in videos
    )

    bloco_ausentes = ""
    if ausentes:
        itens = "".join(f"<li><b>{c.upper()}</b>: {m}</li>" for c, m in ausentes.items())
        bloco_ausentes = (
            '<div style="background:#fff8e1;border-left:4px solid #f9a825;'
            'padding:12px 16px;margin-bottom:16px;border-radius:4px;">'
            '<p style="margin:0 0 6px 0;font-size:13px;font-weight:bold;color:#f57f17;">'
            "⚠️ Canais ausentes hoje</p>"
            f'<ul style="margin:0;padding-left:16px;font-size:12px;color:#555;">{itens}</ul>'
            "</div>"
        )

    html = (
        '<html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222;">'
        + _cabecalho(data_ref, canais_usados)
        + '<div style="background:#f9f9f9;padding:24px 28px;border:1px solid #e0e0e0;border-top:none;">'
        + bloco_ausentes + paragrafos + "</div>"
        + '<div style="padding:16px 28px;border:1px solid #e0e0e0;border-top:none;background:#fff;">'
        '<p style="font-size:12px;color:#888;margin:0 0 8px 0;">Fontes:</p>'
        f'<ul style="font-size:12px;color:#555;margin:0;padding-left:18px;">{fontes}</ul></div>'
        '<p style="font-size:11px;color:#bbb;text-align:center;margin-top:12px;">'
        f'Gerado automaticamente · {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>'
        "</body></html>"
    )

    _enviar(assunto, resumo, html)


def enviar_aviso_sem_digest(data_ref: str, ausentes: dict[str, str]) -> None:
    itens = "".join(f"<li><b>{c.upper()}</b>: {m}</li>" for c, m in ausentes.items())
    html  = (
        '<html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222;">'
        + _cabecalho(data_ref)
        + '<div style="background:#f9f9f9;padding:24px 28px;border:1px solid #e0e0e0;border-top:none;">'
        '<div style="background:#ffebee;border-left:4px solid #c62828;padding:12px 16px;border-radius:4px;">'
        f'<p style="margin:0 0 8px 0;font-weight:bold;color:#b71c1c;">❌ Nenhum morning call disponível para {data_ref}</p>'
        f'<ul style="font-size:13px;color:#555;margin:0;padding-left:16px;">{itens}</ul>'
        "</div></div></body></html>"
    )
    _enviar(
        f"📊 Morning Call Digest — {data_ref} — ❌ Sem conteúdo",
        f"Nenhum morning call disponível para {data_ref}.",
        html,
    )


def enviar_aviso_ip_bloqueado(data_ref: str) -> None:
    html = (
        '<html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222;">'
        + _cabecalho(data_ref)
        + '<div style="background:#f9f9f9;padding:24px 28px;border:1px solid #e0e0e0;border-top:none;">'
        '<div style="background:#fff3e0;border-left:4px solid #e65100;padding:12px 16px;border-radius:4px;">'
        '<p style="margin:0 0 8px 0;font-weight:bold;color:#bf360c;">🚫 IP bloqueado pelo YouTube</p>'
        '<p style="font-size:13px;color:#555;margin:0;">O script detectou bloqueio antes de iniciar e abortou '
        "para não forçar o IP. O bloqueio é temporário — tente rodar manualmente mais tarde.</p>"
        "</div></div></body></html>"
    )
    _enviar(
        f"📊 Morning Call Digest — {data_ref} — 🚫 IP bloqueado",
        f"IP bloqueado pelo YouTube em {data_ref}. Tente manualmente mais tarde.",
        html,
    )
