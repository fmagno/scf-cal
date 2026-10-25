"""Tests for automatic season rollover.

FPB labels seasons "2026/2027" and a season runs 1 August - 31 July. The
scraper derives that label from the run date so it keeps working in 2028 and
beyond without a yearly edit.
"""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scraper  # noqa: E402


class FakeResponse:
    def __init__(self, text=""):
        self.text = text


class SeasonTest(unittest.TestCase):
    def test_season_boundaries(self):
        cases = [
            (date(2026, 7, 31), "2025/2026", date(2026, 7, 31)),
            (date(2026, 8, 1), "2026/2027", date(2027, 7, 31)),
            (date(2026, 10, 25), "2026/2027", date(2027, 7, 31)),
            (date(2026, 12, 31), "2026/2027", date(2027, 7, 31)),
            (date(2027, 1, 1), "2026/2027", date(2027, 7, 31)),
            (date(2027, 7, 31), "2026/2027", date(2027, 7, 31)),
            (date(2027, 8, 1), "2027/2028", date(2028, 7, 31)),
            (date(2028, 10, 1), "2028/2029", date(2029, 7, 31)),
            (date(2029, 6, 15), "2028/2029", date(2029, 7, 31)),
            (date(2030, 8, 15), "2030/2031", date(2031, 7, 31)),
        ]
        for day, epoca, season_end in cases:
            with self.subTest(day=day):
                self.assertEqual(scraper.season_for(day), (epoca, season_end))

    def test_calendar_url_uses_the_given_season(self):
        url = scraper.calendar_url("2028/2029")
        self.assertIn("epoca=2028/2029", url)  # slash stays readable
        self.assertIn("clube=9", url)
        self.assertIn("genero=masculino", url)
        self.assertIn("escalao=S%C3%A9nior", url)

    def test_load_more_sends_the_season_to_fpb(self):
        calls = []

        def fake_fetch(session, url, params=None):
            calls.append((url, params))
            return mock.Mock(json=lambda: {"result": "", "hasmore": False})

        start, end = date(2028, 9, 1), date(2028, 9, 30)
        with mock.patch.object(scraper, "fetch", side_effect=fake_fetch):
            html, has_more = scraper.load_more(
                object(), "2028/2029", start, end
            )

        self.assertEqual((html, has_more), ("", False))
        self.assertEqual(calls[0][0], scraper.AJAX_URL)
        params = calls[0][1]
        self.assertEqual(params["epoca"], "2028/2029")
        self.assertEqual(params["action"], "get_more_days")
        self.assertEqual(params["period[from_date]"], "2028-09-01")
        self.assertEqual(params["period[to_date]"], "2028-09-30")

    def test_scrape_requests_the_season_of_the_run_date(self):
        for day, epoca in [
            (date(2027, 9, 1), "2027/2028"),
            (date(2028, 10, 1), "2028/2029"),
            (date(2029, 1, 15), "2028/2029"),
        ]:
            with self.subTest(day=day):
                fetched = []
                loaded = []

                def fake_fetch(session, url, params=None):
                    fetched.append(url)
                    return FakeResponse("")

                def fake_load_more(session, epoca_arg, start, end):
                    loaded.append((epoca_arg, start, end))
                    return "", False

                with mock.patch.object(
                    scraper, "fetch", side_effect=fake_fetch
                ), mock.patch.object(
                    scraper, "load_more", side_effect=fake_load_more
                ):
                    self.assertEqual(scraper.scrape(today=day), [])

                self.assertEqual(fetched, [scraper.calendar_url(epoca)])
                self.assertTrue(loaded)
                self.assertEqual(loaded[0][0], epoca)

    def test_scrape_stops_crawling_after_the_season_ends(self):
        fetched = []
        loaded = []

        def fake_fetch(session, url, params=None):
            fetched.append(url)
            return FakeResponse("")

        def fake_load_more(session, epoca, start, end):
            loaded.append((epoca, start, end))
            return "", True

        # Season 2027/2028 ends on 31 July; the first AJAX window would start
        # on 18 August, so there is nothing left to crawl.
        with mock.patch.object(
            scraper, "fetch", side_effect=fake_fetch
        ), mock.patch.object(
            scraper, "load_more", side_effect=fake_load_more
        ):
            self.assertEqual(scraper.scrape(today=date(2028, 7, 20)), [])

        self.assertEqual(fetched, [scraper.calendar_url("2027/2028")])
        self.assertEqual(loaded, [])


if __name__ == "__main__":
    unittest.main()
