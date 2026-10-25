"""Tests for the .ics merge logic in scraper.py.

The scenarios here mirror the ways a game can be lost from the feed: it drops
out of the FPB calendar once it has been played, and one bad scrape must never
wipe the published calendar.
"""

import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scraper  # noqa: E402


def make_event(uid, day, time_hm=(20, 30), summary=None):
    """An event dict shaped like scraper.scrape() returns."""
    return {
        "uid": uid,
        "date": day,
        "time": time_hm,
        "home_away": ["SC Farense", "Opponent"],
        "summary": summary or f"SC Farense vs {uid}",
        "location": "Pavilhão do Sporting Clube Farense, Faro",
        "competition": "2ª Divisão Masculina",
        "url": f"https://www.fpb.pt/ficha-de-jogo?internalID={uid.split('@')[0]}",
    }


def make_ics(*events, dtstamp="20260101T000000Z"):
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//test//"]
    for ev in events:
        lines.extend(scraper.serialize_event(ev, dtstamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


class ScraperTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.ics = self.tmp / "farense.ics"
        self.meta = self.tmp / "meta.json"

        patcher = mock.patch.object(scraper, "ICS_PATH", self.ics)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(scraper, "META_PATH", self.meta)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_ics(self, *events):
        self.ics.write_text(make_ics(*events), encoding="utf-8")

    def read(self):
        return self.ics.read_text(encoding="utf-8")

    # ---- the regression that started this: a played game must stay ----

    def test_game_dropped_from_scrape_is_kept_in_the_ics(self):
        yesterday = date.today() - timedelta(days=1)
        next_week = date.today() + timedelta(days=7)
        played = make_event("416303@fpb.pt", yesterday, summary="CBQ Tubarões vs SC Farense")
        upcoming = make_event("416308@fpb.pt", next_week)

        self.write_ics(played)
        existing = scraper.read_existing()

        # The FPB page only lists upcoming days, so yesterday's game is gone
        # from what scrape() returns.
        ics, total, new_count, _updated, _kept = scraper.build_ics(
            [upcoming], existing
        )

        self.assertIn(f"UID:{played['uid']}", ics)
        self.assertIn("SUMMARY:CBQ Tubarões vs SC Farense", ics)
        self.assertIn(f"UID:{upcoming['uid']}", ics)
        self.assertEqual(total, 2)
        self.assertEqual(new_count, 1)

    def test_played_game_survives_repeated_runs(self):
        yesterday = date.today() - timedelta(days=1)
        played = make_event("416303@fpb.pt", yesterday)

        self.write_ics(played)
        ics = self.read()
        for _ in range(3):
            self.ics.write_text(ics, encoding="utf-8")
            ics, total, _new, _updated, _kept = scraper.build_ics(
                [make_event("416308@fpb.pt", date.today() + timedelta(days=7))],
                scraper.read_existing(),
            )
            self.assertIn(f"UID:{played['uid']}", ics)
            self.assertEqual(total, 2)

    def test_events_older_than_retention_are_pruned(self):
        too_old = date.today() - timedelta(days=scraper.RETENTION_DAYS + 10)
        recent = date.today() - timedelta(days=1)
        self.write_ics(
            make_event("old@fpb.pt", too_old),
            make_event("recent@fpb.pt", recent),
        )

        ics, total, _new, _updated, _kept = scraper.build_ics(
            [make_event("new@fpb.pt", date.today() + timedelta(days=7))],
            scraper.read_existing(),
        )

        self.assertNotIn("UID:old@fpb.pt", ics)
        self.assertIn("UID:recent@fpb.pt", ics)
        self.assertIn("UID:new@fpb.pt", ics)
        self.assertEqual(total, 2)

    # ---- normal merge behaviour ----

    def test_new_game_is_added_and_unchanged_game_is_retained(self):
        kept_day = date.today() + timedelta(days=3)
        self.write_ics(make_event("kept@fpb.pt", kept_day))

        ics, total, new_count, updated_count, _kept = scraper.build_ics(
            [
                make_event("kept@fpb.pt", kept_day),
                make_event("new@fpb.pt", date.today() + timedelta(days=5)),
            ],
            scraper.read_existing(),
        )

        self.assertIn("UID:kept@fpb.pt", ics)
        self.assertIn("UID:new@fpb.pt", ics)
        self.assertEqual((total, new_count, updated_count), (2, 1, 0))

    def test_tbd_tip_off_time_is_filled_in(self):
        day = date.today() + timedelta(days=10)
        self.write_ics(make_event("416308@fpb.pt", day, time_hm=None))

        ics, _total, _new, updated_count, _kept = scraper.build_ics(
            [make_event("416308@fpb.pt", day, time_hm=(17, 0))],
            scraper.read_existing(),
        )

        self.assertEqual(updated_count, 1)
        self.assertIn(
            "DTSTART;TZID=Europe/Lisbon:"
            + day.strftime("%Y%m%d")
            + "T170000",
            ics,
        )

    def test_read_existing_unfolds_lines_and_reads_tzid_starts(self):
        day = date.today() + timedelta(days=4)
        self.ics.write_text(
            "\r\n".join(
                [
                    "BEGIN:VCALENDAR",
                    "VERSION:2.0",
                    "PRODID:-//test//",
                    "BEGIN:VEVENT",
                    "UID:416303@fpb.pt",
                    "DTSTAMP:20260101T000000Z",
                    f"DTSTART;TZID=Europe/Lisbon:{day.strftime('%Y%m%d')}T203000",
                    "LOCATION:Pavilhão do Sporting Clube Farense\\, Fa",
                    " ro",
                    "END:VEVENT",
                    "END:VCALENDAR",
                ]
            )
            + "\r\n",
            encoding="utf-8",
        )

        existing = scraper.read_existing()
        self.assertIn("416303@fpb.pt", existing)
        start, lines, _key = existing["416303@fpb.pt"]
        self.assertEqual(start, day)
        self.assertIn(
            "LOCATION:Pavilhão do Sporting Clube Farense\\, Faro", lines
        )

    # ---- failure modes: never lose the published calendar ----

    def test_zero_scraped_games_leaves_the_ics_untouched(self):
        self.write_ics(make_event("416308@fpb.pt", date.today() + timedelta(days=7)))
        before = self.ics.read_bytes()

        with mock.patch.object(scraper, "scrape", return_value=[]):
            with self.assertRaises(SystemExit) as raised:
                scraper.main()

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(self.ics.read_bytes(), before)
        self.assertFalse(self.meta.exists())

    def test_scrape_exception_leaves_the_ics_untouched(self):
        self.write_ics(make_event("416308@fpb.pt", date.today() + timedelta(days=7)))
        before = self.ics.read_bytes()

        with mock.patch.object(scraper, "scrape", side_effect=RuntimeError("boom")):
            with self.assertRaises(SystemExit) as raised:
                scraper.main()

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(self.ics.read_bytes(), before)
        self.assertFalse(self.meta.exists())

    def test_main_writes_ics_and_meta_only_when_changed(self):
        event = make_event("416308@fpb.pt", date.today() + timedelta(days=7))
        # Seed the file exactly as build_ics would produce it.
        self.ics.write_text(
            scraper.build_ics([event], {})[0], encoding="utf-8"
        )
        before = self.ics.read_bytes()

        with mock.patch.object(scraper, "scrape", return_value=[event]):
            scraper.main()
        self.assertEqual(self.ics.read_bytes(), before)
        self.assertFalse(self.meta.exists())

        with mock.patch.object(
            scraper,
            "scrape",
            return_value=[
                event,
                make_event("416999@fpb.pt", date.today() + timedelta(days=9)),
            ],
        ):
            scraper.main()

        self.assertIn("UID:416999@fpb.pt", self.read())
        meta = json.loads(self.meta.read_text(encoding="utf-8"))
        self.assertEqual(meta["events"], 2)
        epoca, _season_end = scraper.season_for(date.today())
        self.assertEqual(meta["source"], scraper.calendar_url(epoca))


if __name__ == "__main__":
    unittest.main()
