# scf-cal

iCalendar (`.ics`) feed of the **SC Farense Senior Men's** basketball games,
automatically generated from the FPB calendar page.

**Subscribe:** `https://fmagno.github.io/scf-cal/farense.ics`

## How it works

- `scraper.py` scrapes `fpb.pt/calendario/clube_9/...` **and validates every game
  individually** — the competition must start with `Sénior Masculino` and one of
  the teams must be Farense. The FPB URL filters are unreliable and are
  deliberately ignored.
- The FPB season (`epoca`) is derived from the run date (1 August – 31 July), so
  the scraper rolls over to `2027/2028`, `2028/2029`, … without a yearly edit.
- The `.ics` is **incremental**: new games are added (by `UID`), existing games
  only change when the data changes (e.g. a "to be defined" tip-off time gets
  set), and games **older than 6 months** are removed — the file never grows
  forever.
- The landing page reads the same `.ics` and keeps a game visible for its
  **whole Lisbon calendar day**, so it does not disappear while the match is
  being played.
- If the FPB page changes and no valid games are found, the script **fails
  without touching** the existing `.ics` (subscribers never lose their calendar).
- A GitHub Action runs **hourly** and only commits when the `.ics` changes.

## Local

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scraper.py
```

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/*.test.js
```

`tests/games.test.js` covers the landing-page date rules — a game stays
visible through its whole Lisbon day, across DST changes and whatever the
viewer's timezone. `tests/test_seasons.py` covers automatic season rollover
(1 August – 31 July, including future seasons such as 2028/2029), and
`tests/test_scraper.py` covers the `.ics` merge: played games are retained
after they drop out of the FPB page, old games are pruned, and a failed or
empty scrape never touches the published file.

## Repository setup (one-time)

1. Push to `github.com/fmagno/scf-cal`
2. Settings → Pages → Source: `main`, folder `/` (root)
3. Settings → Actions → General → Workflow permissions → **Read and write**
