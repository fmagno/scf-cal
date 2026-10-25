const test = require("node:test");
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const path = require("node:path");

const {
  parseEvents,
  parseDTSTART,
  lisbonDay,
  eventDay,
  daysUntil,
  glowStrength,
  formatGameDate,
  upcomingEvents,
} = require("../games.js");

const GAMES_JS = path.join(__dirname, "..", "games.js");
const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;

function timedGame(dtstart, summary = "SC Farense vs Test") {
  return { DTSTART: dtstart, SUMMARY: summary };
}

function allDayGame(dtstart, summary = "SC Farense vs Test") {
  return { DTSTART: dtstart, SUMMARY: summary };
}

test("parseDTSTART reads the wall-clock time but anchors the date in UTC", () => {
  const timed = parseDTSTART("20261024T203000");
  assert.equal(timed.date.toISOString(), "2026-10-24T00:00:00.000Z");
  assert.equal(timed.time, "20:30");
  assert.equal(eventDay(timed), "2026-10-24");

  const allDay = parseDTSTART("20261024");
  assert.equal(allDay.date.toISOString(), "2026-10-24T00:00:00.000Z");
  assert.equal(allDay.time, null);

  assert.equal(parseDTSTART("not a date"), null);
  assert.equal(parseDTSTART(undefined), null);
});

test("parseEvents unfolds lines, ignores parameters and unescapes values", () => {
  const ics = [
    "BEGIN:VCALENDAR",
    "BEGIN:VEVENT",
    "UID:416303@fpb.pt",
    "DTSTART;TZID=Europe/Lisbon:20261024T203000",
    "SUMMARY:CBQ Tubarões vs SC Farense",
    "LOCATION:Pavilhão do Sporting Clube Farense\\, Faro",
    "DESCRIPTION:2ª Divisão Masculina\\nhttps://example.test/game",
    "END:VEVENT",
    "BEGIN:VEVENT",
    "UID:416308@fpb.pt",
    "DTSTART;VALUE=DATE:20261031",
    "SUMMARY:SC Farense vs ACD Ferrag\r\n udo",
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");

  const events = parseEvents(ics);
  assert.equal(events.length, 2);

  assert.equal(events[0].DTSTART, "20261024T203000");
  assert.equal(events[0].SUMMARY, "CBQ Tubarões vs SC Farense");
  assert.equal(
    events[0].LOCATION,
    "Pavilhão do Sporting Clube Farense, Faro"
  );
  assert.equal(
    events[0].DESCRIPTION,
    "2ª Divisão Masculina\nhttps://example.test/game"
  );

  assert.equal(events[1].DTSTART, "20261031");
  assert.equal(events[1].SUMMARY, "SC Farense vs ACD Ferragudo");
});

test("regression: the 24 Oct 2026 game stays visible on game day", () => {
  // It used to vanish at 00:00 UTC (01:00 in Lisbon), hours before tip-off.
  const game = timedGame("20261024T203000", "CBQ Tubarões vs SC Farense");

  for (const iso of [
    "2026-10-23T23:30:00Z", // already 24 Oct in Lisbon
    "2026-10-24T00:00:00Z", // old code dropped it here
    "2026-10-24T00:30:00Z",
    "2026-10-24T19:30:00Z", // tip-off
    "2026-10-24T22:45:00Z", // after the final whistle
  ]) {
    assert.deepEqual(
      upcomingEvents([game], new Date(iso)),
      [game],
      `game should be visible at ${iso}`
    );
  }

  assert.deepEqual(
    upcomingEvents([game], new Date("2026-10-25T00:01:00Z")),
    [],
    "game should be gone once 24 Oct has ended in Lisbon"
  );
});

test("games stay visible for every instant of their Lisbon calendar day", () => {
  const dates = [
    "2026-10-24", // regular day (WEST, UTC+1)
    "2026-10-25", // DST ends at 02:00 local
    "2026-03-29", // DST starts at 01:00 local
    "2026-12-05", // winter (WET, UTC+0)
    "2027-03-28", // next DST start
  ];

  for (const day of dates) {
    const compact = day.replaceAll("-", "");
    const events = [
      timedGame(`${compact}T203000`, `timed ${day}`),
      allDayGame(compact, `time TBD ${day}`),
    ];

    const [year, month, dateOfMonth] = day.split("-").map(Number);
    const from = Date.UTC(year, month - 1, dateOfMonth) - 24 * HOUR;
    for (let t = from; t <= from + 72 * HOUR; t += 30 * MINUTE) {
      const now = new Date(t);
      const expected = lisbonDay(now) <= day;
      const visible = upcomingEvents(events, now).length === events.length;
      assert.equal(
        visible,
        expected,
        `${day}: at ${now.toISOString()} (Lisbon ${lisbonDay(now)}) ` +
          `expected visible=${expected}`
      );
    }
  }
});

test("visibility does not depend on the viewer's timezone", () => {
  const instants = [
    "2026-10-24T00:30:00Z",
    "2026-10-24T22:30:00Z",
    "2026-10-25T00:30:00Z",
  ];
  const script = `
    const { upcomingEvents } = require(${JSON.stringify(GAMES_JS)});
    const game = { DTSTART: "20261024T203000" };
    console.log(JSON.stringify(
      ${JSON.stringify(instants)}.map(
        (iso) => upcomingEvents([game], new Date(iso)).length
      )
    ));
  `;

  const outputs = [
    "Pacific/Kiritimati",
    "America/Los_Angeles",
    "Europe/Lisbon",
    "UTC",
  ].map((tz) =>
    execFileSync(process.execPath, ["-e", script], {
      env: { ...process.env, TZ: tz },
    })
      .toString()
      .trim()
  );

  assert.deepEqual(new Set(outputs).size, 1, `differs by timezone: ${outputs}`);
  assert.equal(outputs[0], "[1,1,0]");
});

test("game dates are English with the month spelled out", () => {
  // Not the viewer's locale ("sábado, 24/10/2026" on a Portuguese phone) and
  // not a numeric date: "Sat, 24 Oct 2026". `today` is passed in so the test
  // does not depend on the day it runs.
  const today = "2026-10-01";
  assert.equal(
    formatGameDate(parseDTSTART("20261024T203000"), today),
    "Sat, 24 Oct 2026"
  );
  assert.equal(
    formatGameDate(parseDTSTART("20261205"), today),
    "Sat, 5 Dec 2026"
  );
  assert.equal(
    formatGameDate(parseDTSTART("20270329T170000"), today),
    "Mon, 29 Mar 2027"
  );
  assert.equal(
    formatGameDate(parseDTSTART("20261101T160000"), today),
    "Sun, 1 Nov 2026"
  );
});

test("daysUntil counts whole Lisbon calendar days to the game", () => {
  const today = "2026-10-24";
  assert.equal(daysUntil(parseDTSTART("20261024T203000"), today), 0);
  assert.equal(daysUntil(parseDTSTART("20261025T160000"), today), 1);
  assert.equal(daysUntil(parseDTSTART("20261030T203000"), today), 6);
  assert.equal(daysUntil(parseDTSTART("20261031T170000"), today), 7);
  assert.equal(daysUntil(parseDTSTART("20261023T203000"), today), -1);
  // Calendar days, not 24-hour periods: DST end/start and month/year rollovers
  // must not produce 0 or 2.
  assert.equal(daysUntil(parseDTSTART("20270329T203000"), "2027-03-28"), 1);
  assert.equal(daysUntil(parseDTSTART("20261025T203000"), "2026-10-24"), 1);
  assert.equal(daysUntil(parseDTSTART("20270101"), "2026-12-31"), 1);
  assert.equal(daysUntil(parseDTSTART("20261101"), "2026-10-31"), 1);
});

test("the static glow fades by one seventh per day", () => {
  assert.equal(glowStrength(1), 6 / 7);
  assert.equal(glowStrength(2), 5 / 7);
  assert.equal(glowStrength(3), 4 / 7);
  assert.equal(glowStrength(4), 3 / 7);
  assert.equal(glowStrength(5), 2 / 7);
  assert.equal(glowStrength(6), 1 / 7);
  // Today is animated and a week away is a regular card.
  assert.equal(glowStrength(0), 0);
  assert.equal(glowStrength(7), 0);
  assert.equal(glowStrength(-1), 0);
});

test("today and tomorrow are labelled instead of dated", () => {
  assert.equal(
    formatGameDate(parseDTSTART("20261024T203000"), "2026-10-24"),
    "Today"
  );
  assert.equal(
    formatGameDate(parseDTSTART("20261025T160000"), "2026-10-24"),
    "Tomorrow"
  );
  // The day after tomorrow is a normal date again.
  assert.equal(
    formatGameDate(parseDTSTART("20261026T203000"), "2026-10-24"),
    "Mon, 26 Oct 2026"
  );
  // Yesterday is not upcoming, but it must not be called "Today" either.
  assert.equal(
    formatGameDate(parseDTSTART("20261023T203000"), "2026-10-24"),
    "Fri, 23 Oct 2026"
  );
});

test("tomorrow rolls over months, years and DST changes", () => {
  assert.equal(
    formatGameDate(parseDTSTART("20261101"), "2026-10-31"),
    "Tomorrow"
  );
  assert.equal(
    formatGameDate(parseDTSTART("20270101"), "2026-12-31"),
    "Tomorrow"
  );
  // DST ends on 25 Oct 2026 and starts on 28 Mar 2027; these are calendar days,
  // so a 23/25-hour day must not shift the label.
  assert.equal(
    formatGameDate(parseDTSTART("20261025T203000"), "2026-10-24"),
    "Tomorrow"
  );
  assert.equal(
    formatGameDate(parseDTSTART("20270329T203000"), "2027-03-28"),
    "Tomorrow"
  );
});

test("the date shown does not depend on the viewer's timezone", () => {
  const script = `
    const { parseDTSTART, formatGameDate } = require(${JSON.stringify(GAMES_JS)});
    console.log(formatGameDate(parseDTSTART("20261024T203000"), "2026-10-01"));
  `;

  const outputs = [
    "Pacific/Kiritimati",
    "America/Los_Angeles",
    "Europe/Lisbon",
    "UTC",
  ].map((tz) =>
    execFileSync(process.execPath, ["-e", script], {
      env: { ...process.env, TZ: tz },
    })
      .toString()
      .trim()
  );

  assert.deepEqual(new Set(outputs), new Set(["Sat, 24 Oct 2026"]));
});

test("today and tomorrow follow the Lisbon calendar, not the viewer's", () => {
  // 22:30 UTC on 24 Oct is still the 24th in Lisbon (UTC+1) but already the
  // 25th in Kiritimati (UTC+14). The game on the 24th is still "Today": the
  // page's day boundary is Lisbon's, like the rest of its date logic.
  const script = `
    const {
      parseDTSTART, lisbonDay, formatGameDate,
    } = require(${JSON.stringify(GAMES_JS)});
    const today = lisbonDay(new Date("2026-10-24T22:30:00Z"));
    console.log(JSON.stringify([
      today,
      formatGameDate(parseDTSTART("20261024T203000"), today),
      formatGameDate(parseDTSTART("20261025T160000"), today),
    ]));
  `;

  const outputs = [
    "Pacific/Kiritimati",
    "America/Los_Angeles",
    "Europe/Lisbon",
    "UTC",
  ].map((tz) =>
    execFileSync(process.execPath, ["-e", script], {
      env: { ...process.env, TZ: tz },
    })
      .toString()
      .trim()
  );

  assert.deepEqual(
    new Set(outputs),
    new Set([JSON.stringify(["2026-10-24", "Today", "Tomorrow"])])
  );
});

test("upcomingEvents keeps future games and drops malformed ones", () => {
  const now = new Date("2026-10-24T12:00:00Z");
  const events = [
    timedGame("20261023T203000", "yesterday"),
    timedGame("20261024T203000", "today"),
    timedGame("20261031T170000", "next week"),
    { SUMMARY: "no DTSTART" },
  ];

  assert.deepEqual(
    upcomingEvents(events, now).map((ev) => ev.SUMMARY),
    ["today", "next week"]
  );
});

test("a time-TBD game remains visible through its whole day", () => {
  const game = allDayGame("20261024", "SC Farense vs TBD");
  assert.deepEqual(upcomingEvents([game], new Date("2026-10-24T00:00:00Z")), [
    game,
  ]);
  assert.deepEqual(upcomingEvents([game], new Date("2026-10-24T22:30:00Z")), [
    game,
  ]);
  assert.deepEqual(upcomingEvents([game], new Date("2026-10-24T23:30:00Z")), []);
});
