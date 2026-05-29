# Morning Call Digest

Automação local que coleta os morning calls de 4 canais financeiros do YouTube, gera um resumo executivo com Gemini e envia por email todo dia útil às 10h30.

**Canais:** BTG Pactual · Genial Investimentos · Investing.com BR · XP Oficial

---

## Como funciona

```
10:25 → Windows acorda o PC automaticamente (se estiver suspenso)
10:30 → Task Scheduler executa run.ps1
        ├── Verifica bloqueio de IP (aborta e notifica se bloqueado)
        ├── yt-dlp lista os últimos 20 vídeos de cada canal
        ├── Consulta a data de cada vídeo individualmente
        ├── Gemini identifica qual é o morning call do dia
        ├── youtube-transcript-api baixa as transcrições
        ├── Gemini gera resumo executivo em 3–4 parágrafos
        └── Email HTML enviado via Gmail SMTP
~11:00 → Script termina, PC volta a suspender após 30s
```

> Os morning calls são transmitidos ao vivo entre 9h e 10h. O YouTube leva 30–90 min para processar as legendas automáticas do VOD. Rodar às 10h30 já cobre a maioria dos canais; os que ainda não têm transcrição são retentados por até 20 minutos antes de serem marcados como ausentes.

---

## Pré-requisitos

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) instalado e no PATH
- Conta Google com [Gemini API Key](https://aistudio.google.com/app/apikey)
- Conta Gmail com [Senha de App](https://myaccount.google.com/apppasswords) (requer 2FA ativo)

---

## Instalação

### 1. Clone e instale dependências

```powershell
git clone <url-do-repo>
cd morning-call-digest
pip install -r requirements.txt
```

### 2. Configure os segredos

```powershell
Copy-Item secrets.env.example secrets.env
notepad secrets.env
```

```env
GEMINI_API_KEY=sua_chave_aqui
EMAIL_REMETENTE=seu_email@gmail.com
EMAIL_SENHA_APP=xxxx xxxx xxxx xxxx
```

> `secrets.env` está no `.gitignore` e nunca será commitado.

### 3. Configure os destinatários

Edite [config.json](config.json):

```json
{
  "destinatarios": [
    "voce@gmail.com",
    "outro@email.com"
  ]
}
```

### 4. Teste manualmente

```powershell
$env:TEST_MODE = "true"   # envia só para o remetente
.\run.ps1
```

---

## Agendamento automático (Windows Task Scheduler)

O script roda **localmente** para evitar bloqueios de IP que afetam ambientes de CI/CD.

### Configurar as tarefas

Execute **como Administrador**:

```powershell
.\setup_task.ps1
```

Cria duas tarefas no Windows:

| Tarefa | Horário | Função |
|--------|---------|--------|
| `MorningCallDigest_Wake` | 10:25 seg–sex | Acorda o PC (WakeToRun habilitado) |
| `MorningCallDigest_Run`  | 10:30 seg–sex | Executa o script |

> Apenas a tarefa `_Wake` tem WakeToRun habilitado. A `_Run` não precisa — o PC já está acordado quando ela dispara.

### Requisitos para o wake funcionar

- PC **plugado na tomada**
- Suspensão **S3** (não hibernação S4, não desligado)
- Wake timers habilitados no plano de energia:

```powershell
powercfg /query SCHEME_CURRENT SUB_SLEEP RTCWAKE
```

Se o valor for `000`, habilite via:
> Opções de Energia → Alterar configurações do plano → Configurações de energia avançadas → Suspender → Permitir temporizadores de ativação → **Habilitar**

### Remover as tarefas

```powershell
Unregister-ScheduledTask -TaskName "MorningCallDigest_Wake" -Confirm:$false
Unregister-ScheduledTask -TaskName "MorningCallDigest_Run"  -Confirm:$false
```

---

## Estrutura do projeto

```
morning-call-digest/
├── main.py              # orquestração do pipeline
├── config.py            # constantes, env vars, cliente Gemini
├── youtube.py           # busca de vídeos, transcrições, IP check
├── summarizer.py        # geração do resumo com Gemini
├── emailer.py           # construção e envio de emails
├── run.ps1              # wrapper: carrega secrets, roda main.py, suspende PC
├── setup_task.ps1       # registra tarefas no Task Scheduler (rodar como Admin)
├── config.json          # lista de destinatários
├── secrets.env          # credenciais (não commitado)
├── secrets.env.example  # template
└── requirements.txt     # dependências Python
```

---

## Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `GEMINI_API_KEY` | Chave da [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `EMAIL_REMETENTE` | Endereço Gmail do remetente |
| `EMAIL_SENHA_APP` | [Senha de app](https://myaccount.google.com/apppasswords) do Gmail (16 chars) |
| `TEST_MODE` | Se `true`, envia email só para o remetente |
