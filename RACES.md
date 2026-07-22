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
```

`start`/`finish` are `name, latitude, longitude` (city centre). `from`/`to` are inclusive
`YYYY-MM-DD` dates. Optional per-race overrides: `- max gap: 10` (km allowed between two
consecutive rides) and `- max radius: 20` (km a start/finish may be from the city centre).
Headings inside a fenced code block (like the example above) are ignored.

---

## Hamburg → Berlin
- start: Hamburg, 53.5511, 9.9937
- finish: Berlin, 52.5200, 13.4050
- from: 2005-01-01
- to: 2030-12-31

## Berlin → Prague
- start: Berlin, 52.5200, 13.4050
- finish: Prague, 50.0755, 14.4378
- from: 2005-01-01
- to: 2030-12-31

## Prague → Vienna
- start: Prague, 50.0755, 14.4378
- finish: Vienna, 48.2082, 16.3738
- from: 2005-01-01
- to: 2030-12-31

## Vienna → Budapest
- start: Vienna, 48.2082, 16.3738
- finish: Budapest, 47.4979, 19.0402
- from: 2005-01-01
- to: 2030-12-31

## Vienna → Ljubljana
- start: Vienna, 48.2082, 16.3738
- finish: Ljubljana, 46.0569, 14.5058
- from: 2005-01-01
- to: 2030-12-31

## Stuttgart → Munich
- start: Stuttgart, 48.7758, 9.1829
- finish: Munich, 48.1372, 11.5755
- from: 2005-01-01
- to: 2030-12-31

## Leipzig → Dresden
- start: Leipzig, 51.3397, 12.3731
- finish: Dresden, 51.0504, 13.7373
- from: 2005-01-01
- to: 2030-12-31

## Kraków → Warsaw
- start: Kraków, 50.0647, 19.9450
- finish: Warsaw, 52.2297, 21.0122
- from: 2005-01-01
- to: 2030-12-31

## Paris → Barcelona
- start: Paris, 48.8566, 2.3522
- finish: Barcelona, 41.3874, 2.1686
- from: 2005-01-01
- to: 2030-12-31
