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
- start: Berlin, Germany, 52.5200, 13.4050
- finish: Amsterdam, Netherlands, 52.3731, 4.8922
- from: 2015-01-01
- to: 2030-12-31
- name: Tramprennen
```

`start`/`finish` are `city, country, latitude, longitude` (city centre). The country is
required — half the interesting city names exist in several countries. `from`/`to` are
inclusive `YYYY-MM-DD` dates.

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
- start: Berlin, Germany, 52.5200, 13.4050
- finish: Prague, Czechia, 50.0755, 14.4378
- from: 2026-07-01
- to: 2026-07-31

## Utrecht → Rotterdam
- start: Utrecht, Netherlands, 52.0907, 5.1214
- finish: Rotterdam, Netherlands, 51.9244, 4.4777
- from: 2026-07-01
- to: 2026-07-31

## Jena → Munich
- start: Jena, Germany, 50.9271, 11.5892
- finish: Munich, Germany, 48.1372, 11.5755
- from: 2026-08-01
- to: 2026-08-31

## Lüneburg → Pui
- start: Lüneburg, Germany, 53.2464, 10.4115
- finish: Pui, Romania, 45.5147, 23.0806
- from: 2026-08-22
- to: 2026-09-03
- name: Tramprennen

## Weiden in der Oberpfalz → Pui
- start: Weiden in der Oberpfalz, Germany, 49.6767, 12.1561
- finish: Pui, Romania, 45.5147, 23.0806
- from: 2026-08-22
- to: 2026-09-03
- name: Tramprennen

## Hurum Forest → Føyno
- start: Hurum Forest, Norway, 59.6000, 10.4200
- finish: Føyno, Norway, 59.7386, 5.4072
- from: 2026-07-22
- to: 2026-08-08

## Føyno → Fontpedrouse
- start: Føyno, Norway, 59.7386, 5.4072
- finish: Fontpedrouse, France, 42.5347, 2.1836
- from: 2026-08-01
- to: 2026-08-31

## Rome → Naples
- start: Rome, Italy, 41.8931, 12.4828
- finish: Naples, Italy, 40.8358, 14.2486
- from: 2026-09-01
- to: 2026-09-30

## Hengelo → Bochum
- start: Hengelo, Netherlands, 52.2656, 6.7931
- finish: Bochum, Germany, 51.4819, 7.2158
- from: 2026-10-01
- to: 2026-10-31

## Tours → Nantes
- start: Tours, France, 47.3936, 0.6892
- finish: Nantes, France, 47.2181, -1.5528
- from: 2026-11-01
- to: 2026-11-30

## Uničov → Wrocław
- start: Uničov, Czechia, 49.7708, 17.1214
- finish: Wrocław, Poland, 51.1100, 17.0325
- from: 2026-12-01
- to: 2026-12-31

## Tábor → Prague
- start: Tábor, Czechia, 49.4144, 14.6578
- finish: Prague, Czechia, 50.0875, 14.4214
- from: 2027-01-01
- to: 2027-01-31

## Cambridge → Leicester
- start: Cambridge, United Kingdom, 52.2050, 0.1225
- finish: Leicester, United Kingdom, 52.6361, -1.1331
- from: 2027-02-01
- to: 2027-02-28

## Tartu → Riga
- start: Tartu, Estonia, 58.3800, 26.7225
- finish: Riga, Latvia, 56.9475, 24.1069
- from: 2027-03-01
- to: 2027-03-31

## Bremen → Hannover
- start: Bremen, Germany, 53.0758, 8.8072
- finish: Hannover, Germany, 52.3667, 9.7167
- from: 2027-04-01
- to: 2027-04-30

## Grenoble → Lyon
- start: Grenoble, France, 45.1715, 5.7224
- finish: Lyon, France, 45.7600, 4.8400
- from: 2027-05-01
- to: 2027-05-31

## Sheffield → Manchester
- start: Sheffield, United Kingdom, 53.3808, -1.4703
- finish: Manchester, United Kingdom, 53.4790, -2.2452
- from: 2027-06-01
- to: 2027-06-30

## Karlsruhe → Mannheim
- start: Karlsruhe, Germany, 49.0092, 8.4040
- finish: Mannheim, Germany, 49.4878, 8.4661
- from: 2027-07-01
- to: 2027-07-31

## Hengelo → Münster
- start: Hengelo, Netherlands, 52.2656, 6.7931
- finish: Münster, Germany, 51.9625, 7.6256
- from: 2027-08-01
- to: 2027-08-31

## Limerick → Dublin
- start: Limerick, Ireland, 52.6653, -8.6238
- finish: Dublin, Ireland, 53.3497, -6.2603
- from: 2027-09-01
- to: 2027-09-30

## Essen → Cologne
- start: Essen, Germany, 51.4508, 7.0131
- finish: Cologne, Germany, 50.9364, 6.9528
- from: 2027-10-01
- to: 2027-10-31
