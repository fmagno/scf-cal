#!/usr/bin/env python3
"""Scrape the Farense senior men's calendar from fpb.pt and maintain farense.ics."""

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = (
    "https://www.fpb.pt/calendario/clube_9/"
    "?clube=9&epoca=2026/2027&genero=masculino&escalao=S%C3%A9nior&"
)
ICS_PATH = Path(__file__).resolve().parent / "farense.ics"
META_PATH = Path(__file__).resolve().parent / "meta.json"

MONTHS = {
    "JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12,
}
RETENTION_DAYS = 183  # ~6 months, based on event date
SENIOR_MASC_RE = re.compile(r"^\s*S[eé]nior\s+Masculino\b", re.IGNORECASE)
TIME_RE = re.compile(r"^([01]?\d|2[0-3])H([0-5]\d)$")
DATE_RE = re.compile(r"^(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})$")
DTSTART_RE = re.compile(r"^DTSTART[^:]*:(\d{8})(?:T(\d{6}))?", re.MULTILINE)
UID_RE = re.compile(r"^UID:(.+)$", re.MULTILINE)
DTSTAMP_RE = re.compile(r"^DTSTAMP[^:]*:.*$", re.MULTILINE)

USER_AGENT = "scf-cal/1.0 (+https://github.com/fmagno/scf-cal)"


def parse_date(text):
    m = DATE_RE.match(text.strip())
    if not m:
        return None
    day, mon, year = int(m.group(1)), MONTHS.get(m.group(2).upper()), int(m.group(3))
    if mon is None:
        return None
    return date(year, mon, day)


def scrape():
    resp = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events = []
    skipped_no_date = 0
    for row in soup.select("div.day-wrapper"):
        date_hdr = row.select_one("h3.date")
        event_date = parse_date(date_hdr.get_text(" ", strip=True)) if date_hdr else None
        for game in row.select("a.game-wrapper-a"):
            comp_el = game.select_one("div.competition span")
            competition = comp_el.get_text(" ", strip=True) if comp_el else ""

            # Never trust the URL filters: validate each event itself.
            if not SENIOR_MASC_RE.match(competition):
                continue
            siglas = [s.get_text(" ", strip=True) for s in game.select("span.sigla")]
            if not any("farense" in s.lower() for s in siglas):
                continue
            if len(siglas) < 2:
                continue

            if event_date is None:
                skipped_no_date += 1
                continue

            time_el = game.select_one("div.hour h3")
            time_text = time_el.get_text(" ", strip=True) if time_el else ""
            tm = TIME_RE.match(time_text)
            time_hm = (int(tm.group(1)), int(tm.group(2))) if tm else None

            loc_el = game.select_one("div.location-wrapper b")
            location = ""
            if loc_el:
                loc_text = re.sub(r"\s+", " ", loc_el.get_text(" ", strip=True))
                if "," in loc_text:
                    venue, city = loc_text.rsplit(",", 1)
                    location = f"{venue.strip()}, {city.strip()}"
                else:
                    location = loc_text

            uid_m = re.search(r"internalID=(\d+)", game.get("href", ""))
            if not uid_m:
                continue

            events.append({
                "uid": f"{uid_m.group(1)}@fpb.pt",
                "date": event_date,
                "time": time_hm,
                "home_away": siglas,
                "summary": f"{siglas[0]} vs {siglas[1]}",
                "location": location,
                "competition": competition.split("|", 1)[-1].strip(),
                "url": f"https://www.fpb.pt/ficha-de-jogo?internalID={uid_m.group(1)}",
            })

    if skipped_no_date:
        print(f"warn: skipped {skipped_no_date} game(s) with no date")
    return events


def esc(text):
    return (
        text.replace("\\", "\\\\").replace(";", "\\;")
        .replace(",", "\\,").replace("\n", "\\n")
    )


def fold(line):
    """Fold one logical line into <=75-octet physical lines (RFC 5545)."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return [line]
    out = []
    limit = 75
    while data:
        cut = min(limit, len(data))
        while cut > 0:
            try:
                text = data[:cut].decode("utf-8")
                break
            except UnicodeDecodeError:
                cut -= 1
        out.append(text if not out else " " + text)
        data = data[cut:]
        limit = 74  # continuation lines: 1 space + <=74 content octets
    return out


def serialize_event(ev, dtstamp):
    lines = [
        "BEGIN:VEVENT",
        f"UID:{ev['uid']}",
        f"DTSTAMP:{dtstamp}",
    ]
    if ev["time"]:
        start = datetime(ev["date"].year, ev["date"].month, ev["date"].day,
                         ev["time"][0], ev["time"][1])
        end = start + timedelta(hours=2)
        lines += [
            "DTSTART;TZID=Europe/Lisbon:" + start.strftime("%Y%m%dT%H%M%S"),
            "DTEND;TZID=Europe/Lisbon:" + end.strftime("%Y%m%dT%H%M%S"),
        ]
    else:
        lines += [
            "DTSTART;VALUE=DATE:" + ev["date"].strftime("%Y%m%d"),
            "DTEND;VALUE=DATE:" + (ev["date"] + timedelta(days=1)).strftime("%Y%m%d"),
        ]
    lines += [
        f"SUMMARY:{esc(ev['summary'])}",
    ]
    if ev["location"]:
        lines.append(f"LOCATION:{esc(ev['location'])}")
    lines += [
        f"DESCRIPTION:{esc(ev['competition'])}\\n{esc(ev['url'])}",
        f"URL:{ev['url']}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "END:VEVENT",
    ]
    return lines


def read_existing():
    """Return {uid: (start_date, lines, content_key)} from the current .ics."""
    if not ICS_PATH.exists():
        return {}
    text = ICS_PATH.read_text(encoding="utf-8")
    text = re.sub(r"\r\n[ \t]|\n[ \t]|\r[ \t]", "", text)
    blocks = re.findall(r"BEGIN:VEVENT.*?END:VEVENT", text, re.S)
    result = {}
    for block in blocks:
        uid_m = UID_RE.search(block)
        ds_m = DTSTART_RE.search(block)
        if not uid_m or not ds_m:
            continue
        start = datetime.strptime(ds_m.group(1), "%Y%m%d").date()
        lines = block.split("\n")
        lines = [l.rstrip("\r") for l in lines]
        result[uid_m.group(1).strip()] = (
            start, lines, DTSTAMP_RE.sub("", "\n".join(lines))
        )
    return result


def build_ics(events, existing):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).date()
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    merged = {}
    kept = 0
    for uid, (start, lines, key) in existing.items():
        if start < cutoff:
            print(f"prune: {uid} ({start.isoformat()}) older than 6 months")
            continue
        merged[uid] = (start, lines, key)
        kept += 1

    new_count = 0
    updated_count = 0
    for ev in events:
        lines = serialize_event(ev, now_stamp)
        key = DTSTAMP_RE.sub("", "\n".join(lines))
        if ev["uid"] in merged:
            start, old_lines, old_key = merged[ev["uid"]]
            if old_key == key:
                merged[ev["uid"]] = (start, old_lines, old_key)  # unchanged
            else:
                merged[ev["uid"]] = (ev["date"], lines, key)
                updated_count += 1
        else:
            merged[ev["uid"]] = (ev["date"], lines, key)
            new_count += 1

    def sort_key(item):
        start, lines, _ = item[1]
        summary = next((l for l in lines if l.startswith("SUMMARY:")), "")
        return (start, summary)

    header = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//scf-cal//FPB Farense Senior//PT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:SC Farense Sénior Masculino",
        "X-WR-TIMEZONE:Europe/Lisbon",
        "BEGIN:VTIMEZONE",
        "TZID:Europe/Lisbon",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:+0000",
        "TZOFFSETTO:+0100",
        "TZNAME:WEST",
        "DTSTART:19700329T010000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0100",
        "TZOFFSETTO:+0000",
        "TZNAME:WET",
        "DTSTART:19701025T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
    body = []
    for _uid, (_start, lines, _key) in sorted(merged.items(), key=sort_key):
        for line in lines:
            body.extend(fold(line))

    all_lines = header + body + ["END:VCALENDAR"]
    return "\r\n".join(all_lines) + "\r\n", len(merged), new_count, updated_count, kept


def main():
    try:
        events = scrape()
    except Exception as exc:
        print(f"error: fetch/parse failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if not events:
        print("error: 0 valid senior-men Farense games found; not touching existing .ics",
              file=sys.stderr)
        sys.exit(1)

    existing = read_existing()
    ics, total, new_count, updated_count, kept = build_ics(events, existing)

    old = ICS_PATH.read_bytes() if ICS_PATH.exists() else None
    if old != ics.encode("utf-8"):
        ICS_PATH.write_bytes(ics.encode("utf-8"))
        print(f"wrote {ICS_PATH.name}: {total} events "
              f"({new_count} new, {updated_count} updated, {kept} retained)")
        # Only refreshed when the calendar changes, so CI does not commit hourly.
        META_PATH.write_text(json.dumps({
            "last_run": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "events": total,
            "source": URL,
        }, indent=2) + "\n", encoding="utf-8")
    else:
        print(f"no change: {ICS_PATH.name} already up to date ({total} events)")


if __name__ == "__main__":
    main()
