/* Calendar logic for the SC Farense landing page.
 *
 * Kept in its own file, free of DOM code, so the same functions the page runs
 * are the ones covered by tests/games.test.js.
 *
 * farense.ics stores games as wall-clock times in Europe/Lisbon (DTSTART
 * carries TZID=Europe/Lisbon, not an instant), so "has this game passed?" is
 * answered on the Lisbon calendar day. Comparing DTSTART with Date.now() would
 * drop a game at 00:00 UTC on game day.
 */

function unescapeICS(v) {
  return v.replace(/\\n/g, "\n").replace(/\\([\\;,])/g, "$1");
}

function parseEvents(text) {
  const lines = text.replace(/\r\n[ \t]/g, "").replace(/\r[ \t]/g, "").split("\n");
  const events = [];
  let cur = null;
  for (const raw of lines) {
    const line = raw.replace(/\r$/, "");
    if (line === "BEGIN:VEVENT") { cur = {}; continue; }
    if (line === "END:VEVENT") { if (cur) events.push(cur); cur = null; continue; }
    if (!cur) continue;
    const i = line.indexOf(":");
    if (i < 1) continue;
    const name = line.slice(0, i).split(";")[0];
    if (["DTSTART", "SUMMARY", "LOCATION", "DESCRIPTION", "URL"].includes(name)) {
      cur[name] = unescapeICS(line.slice(i + 1));
    }
  }
  return events;
}

function parseDTSTART(v) {
  const m = /^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2}))?/.exec(v || "");
  if (!m) return null;
  return {
    date: new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])),
    time: m[4] ? `${m[4]}:${m[5]}` : null,
  };
}

const LISBON_DAY = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Lisbon", year: "numeric", month: "2-digit", day: "2-digit",
});

// YYYY-MM-DD of the given instant as seen in Lisbon.
function lisbonDay(instant) {
  const parts = Object.fromEntries(
    LISBON_DAY.formatToParts(instant).map((p) => [p.type, p.value])
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

// The date written in DTSTART, e.g. "2026-10-24".
function eventDay(dt) {
  return dt.date.toISOString().slice(0, 10);
}

function isPast(dt, today) {
  return eventDay(dt) < today;
}

// Past games stay in the .ics (6-month retention), but the landing page only
// shows what's still ahead. A game stays visible for its whole Lisbon calendar
// day, so it never disappears while it is being played.
function upcomingEvents(events, now = new Date()) {
  const today = lisbonDay(now);
  return events.filter((ev) => {
    const dt = parseDTSTART(ev.DTSTART);
    return dt && !isPast(dt, today);
  });
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    unescapeICS,
    parseEvents,
    parseDTSTART,
    lisbonDay,
    eventDay,
    isPast,
    upcomingEvents,
  };
}
