# scf-ics

Calendário `.ics` dos jogos do **Sénior Masculino do Sporting Clube Farense**,
gerado automaticamente a partir da página de calendário da FPB.

**Subscrever:** `https://fmagno.github.io/scf-ics/farense.ics`

## Como funciona

- `scraper.py` faz *scrape* de `fpb.pt/calendario/clube_9/...` **e valida cada jogo
  individualmente** — a competição tem de começar por `Sénior Masculino` e uma das
  equipas tem de ser o Farense. Os filtros do URL da FPB não são fiáveis e são
  ignorados de propósito.
- O `.ics` é **incremental**: jogos novos entram (por `UID`), jogos já existentes
  só mudam quando os dados mudam (ex.: horário de "a definir" passa a definido),
  e jogos com **mais de 6 meses** são removidos — o ficheiro não cresce para sempre.
- Se a página da FPB mudar e nenhum jogo válido for encontrado, o script **falha
  sem tocar** no `.ics` existente (os subscritos nunca ficam sem calendário).
- Um GitHub Action corre **de hora a hora** e só faz *commit* se o `.ics` mudar.

## Local

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scraper.py
```

## Setup repositório (uma vez)

1. Push para `github.com/fmagno/scf-ics`
2. Settings → Pages → Source: `main`, pasta `/` (raiz)
3. Settings → Actions → General → Workflow permissions → **Read and write**
