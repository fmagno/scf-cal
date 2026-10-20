# scf-ics

iCalendar (`.ics`) feed of the **SC Farense Senior Men's** basketball games,
automatically generated from the FPB calendar page.

**Subscribe:** `https://fmagno.github.io/scf-ics/farense.ics`

## How it works

- `scraper.py` scrapes `fpb.pt/calendario/clube_9/...` **and validates every game
  individually** — the competition must start with `Sénior Masculino` and one of
  the teams must be Farense. The FPB URL filters are unreliable and are
  deliberately ignored.
- The `.ics` is **incremental**: new games are added (by `UID`), existing games
  only change when the data changes (e.g. a "to be defined" tip-off time gets
  set), and games **older than 6 months** are removed — the file never grows
  forever.
- If the FPB page changes and no valid games are found, the script **fails
  without touching** the existing `.ics` (subscribers never lose their calendar).
- A GitHub Action runs **hourly** and only commits when the `.ics` changes.

## Local

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scraper.py
```

## Repository setup (one-time)

1. Push to `github.com/fmagno/scf-ics`
2. Settings → Pages → Source: `main`, folder `/` (root)
3. Settings → Actions → General → Workflow permissions → **Read and write**
