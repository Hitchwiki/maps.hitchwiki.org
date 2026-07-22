# Races

A **race** is a city pair plus a timespan. Anyone who hitchhiked from the first city to
the second one inside that timespan is ranked by how long the journey took — fastest
first. `/races` shows the podium (top 3) of every race that is **running right now**, plus
the ones **starting within the next month** (marked "starts in N days", with no board
yet). Races that have ended, and races further out than a month, are not listed — leave
them in this file, they simply stop and start showing on their own dates.

The standings are computed from logged rides by `hitch/scripts/races.py` (run as part of
`show.py`, written to `dist/races.json`). A hitchhiker's journey is a chain of their own
consecutive rides where:

* the **first ride starts within 20 km** of the start city centre,
* the **last ride ends within 20 km** of the finish city centre,
* each ride starts **within 10 km** of where the previous one dropped them off,
* each ride departs **after** the previous one arrived, and at most **48 h** later,
* every ride carries a real username, a logged destination and a departure time,
* every ride lies inside the race timespan.

The journey time is `arrival of the last ride − departure of the first ride`, i.e. waiting
time counts. Hardly anyone logs arrival times (a few hundred rides out of 75k), so a
missing arrival is estimated from the leg's distance at 75 km/h; entries containing such a
leg are marked "partly estimated" on the page. If someone did the route several times,
only their fastest attempt is ranked.

## Format

One `##` heading per race — the heading is the race name — followed by these keys:

```
## Berlin → Amsterdam
- start: Berlin, 52.5200, 13.4050
- finish: Amsterdam, 52.3731, 4.8922
- from: 2015-01-01
- to: 2030-12-31
- name: Tramprennen
```

`start`/`finish` are `name, latitude, longitude` (city centre). `from`/`to` are inclusive
`YYYY-MM-DD` dates.

`name` is the event the race belongs to, and is optional: the page titles a race
`<name> <heading>` — "Tramprennen Berlin → Amsterdam" — and falls back to
"Virtual race Berlin → Amsterdam" when no event organised it.

Optional per-race overrides: `- max gap: 10` (km allowed between two consecutive rides)
and `- max radius: 20` (km a start/finish may be from the city centre). Headings inside a
fenced code block (like the example above) are ignored.

---

Races are picked to be worth racing: a stretch between two big cities that at least one
hitchhiker has already completed inside the race window, so every board opens with a time
to beat rather than empty.

## Berlin → Prague
- start: Berlin, 52.5200, 13.4050
- finish: Prague, 50.0755, 14.4378
- from: 2026-07-01
- to: 2026-07-31

## Utrecht → Rotterdam
- start: Utrecht, 52.0907, 5.1214
- finish: Rotterdam, 51.9244, 4.4777
- from: 2026-07-01
- to: 2026-07-31
