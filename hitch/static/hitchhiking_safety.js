// The /hitchhiking-safety page: pick a cohort of hitchhikers at the top, and every
// breakdown below re-derives itself from the rides that cohort actually rode.
//
// All filtering is client-side over dist/hitchhiking_safety.json (~1.1k rows, the rides
// that carry an answer at all). The cohort is combinatorial — four person slots x gender
// x age x experience — so no server-side aggregate could answer it without either
// exploding or deciding in advance which questions are askable. The arithmetic lives in
// safety_stats.js so it can be tested under Node; this file is DOM only.
(function () {
  "use strict";

  const S = window.SafetyStats;
  const L = window.__SAFETY_LABELS__ || {};
  const MAX_PEOPLE = 4;
  const GENDERS = ["female", "male", "non_binary", "prefer_not_to_say", "unknown"];

  let DATA = { rides: [], coverage: {}, negative_experiences: {}, min_sample: 10 };
  let filters = [emptyFilter()];
  let exactSize = false;

  function t(key, fallback) {
    return L[key] != null ? L[key] : fallback != null ? fallback : key;
  }

  function emptyFilter() {
    return { genders: [], ageMin: null, ageMax: null, ageUnknownOk: false, expMin: null, expMax: null, expUnknownOk: false };
  }

  // -- cohort UI ------------------------------------------------------------

  function renderPersonCards() {
    const host = document.getElementById("person-cards");
    host.innerHTML = "";
    filters.forEach((filter, index) => host.appendChild(personCard(filter, index)));
    const addButton = document.getElementById("add-person");
    addButton.disabled = filters.length >= MAX_PEOPLE;
    // The wording has to say what adding one MEANS, not just that you can: a second card
    // is a second *person in the same car*, not a second cohort to compare against.
    addButton.textContent =
      filters.length >= MAX_PEOPLE ? t("max_people", "Up to 4 hitchhikers") : t("add_person", "+ Add another hitchhiker");
    document.getElementById("exact-size-row").hidden = false;
  }

  function personCard(filter, index) {
    const card = document.createElement("div");
    card.className = "cohort-card";

    const head = document.createElement("div");
    head.className = "cohort-card-head";
    const title = document.createElement("strong");
    title.textContent = t("person_n", "Hitchhiker {n}").replace("{n}", index + 1);
    head.appendChild(title);
    if (filters.length > 1) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "cohort-remove";
      remove.setAttribute("aria-label", t("remove_person", "Remove this hitchhiker"));
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        filters.splice(index, 1);
        renderPersonCards();
        render();
      });
      head.appendChild(remove);
    }
    card.appendChild(head);

    const chips = document.createElement("div");
    chips.className = "cohort-chips";
    GENDERS.forEach((gender) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "cohort-chip" + (filter.genders.indexOf(gender) !== -1 ? " is-on" : "");
      chip.setAttribute("aria-pressed", filter.genders.indexOf(gender) !== -1 ? "true" : "false");
      chip.textContent = genderLabel(gender);
      chip.addEventListener("click", () => {
        const at = filter.genders.indexOf(gender);
        if (at === -1) filter.genders.push(gender);
        else filter.genders.splice(at, 1);
        renderPersonCards();
        render();
      });
      chips.appendChild(chip);
    });
    card.appendChild(chips);

    card.appendChild(
      rangeRow(t("age", "Age"), filter, "ageMin", "ageMax", "ageUnknownOk", t("age_hint", "years, at the time of the ride")),
    );
    card.appendChild(
      rangeRow(
        t("experience", "Hitchhiking experience"),
        filter,
        "expMin",
        "expMax",
        "expUnknownOk",
        t("experience_hint", "years since their first ride"),
      ),
    );
    return card;
  }

  function rangeRow(label, filter, minKey, maxKey, unknownKey, hint) {
    const row = document.createElement("div");
    row.className = "cohort-range";

    const caption = document.createElement("label");
    caption.textContent = label;
    row.appendChild(caption);

    [minKey, maxKey].forEach((key) => {
      const input = document.createElement("input");
      input.type = "number";
      input.min = "0";
      input.max = "99";
      input.placeholder = key === minKey ? t("from", "from") : t("to", "to");
      input.value = filter[key] == null ? "" : filter[key];
      input.addEventListener("change", () => {
        const value = input.value === "" ? null : Number(input.value);
        filter[key] = value == null || Number.isNaN(value) ? null : value;
        renderPersonCards();
        render();
      });
      row.appendChild(input);
    });

    const note = document.createElement("span");
    note.className = "cohort-hint";
    note.textContent = hint;
    row.appendChild(note);

    // Only offered once a bound is actually set. Unrecorded values are excluded by
    // default from a narrowed range (safety_stats.rangeMatches): a band that quietly
    // swept in everyone whose age nobody wrote down would not be that band.
    if (filter[minKey] != null || filter[maxKey] != null) {
      const wrap = document.createElement("label");
      wrap.className = "cohort-unknown";
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = !!filter[unknownKey];
      box.addEventListener("change", () => {
        filter[unknownKey] = box.checked;
        render();
      });
      wrap.appendChild(box);
      wrap.appendChild(document.createTextNode(" " + t("include_unrecorded", "include rides where this wasn’t recorded")));
      row.appendChild(wrap);
    }
    return row;
  }

  function genderLabel(gender) {
    return t("gender_" + gender, gender);
  }

  // -- rendering ------------------------------------------------------------

  function matching() {
    return DATA.rides.filter((ride) => S.matchCohort(ride, filters, exactSize));
  }

  function percent(rate) {
    return rate == null ? "—" : Math.round(rate * 100) + "%";
  }

  function renderHeadline(rides) {
    const stats = S.summarise(rides);
    const host = document.getElementById("headline");
    host.innerHTML = "";
    if (!stats.rides) {
      host.appendChild(note(t("empty", "No ride with an answer matches this cohort yet. Widen it above.")));
      return stats;
    }
    const cards = [
      [percent(stats.rate), t("would_again", "would ride again")],
      [String(stats.rides), t("answers", "answers")],
      [String(stats.no), t("said_no", "said no")],
      [String(stats.people), t("named_people", "named hitchhikers")],
    ];
    const grid = document.createElement("div");
    grid.className = "stats-summary";
    cards.forEach(([value, caption]) => {
      const card = document.createElement("div");
      card.className = "stats-card";
      const strong = document.createElement("strong");
      strong.textContent = value;
      const span = document.createElement("span");
      span.textContent = caption;
      card.appendChild(strong);
      card.appendChild(span);
      grid.appendChild(card);
    });
    host.appendChild(grid);
    if (stats.ci) {
      host.appendChild(
        note(
          t("ci", "95% confidence interval: {lo}–{hi}. With this many answers, that range is the honest answer, not the single percentage above.")
            .replace("{lo}", percent(stats.ci[0]))
            .replace("{hi}", percent(stats.ci[1])),
        ),
      );
    }
    return stats;
  }

  function note(text) {
    const paragraph = document.createElement("p");
    paragraph.className = "stats-note";
    paragraph.textContent = text;
    return paragraph;
  }

  // Every breakdown is the same question asked of a different column, so they share one
  // renderer: what fraction of THIS cohort's answers were "yes", cut by that column.
  function renderBreakdown(host, title, rides, keyFn, labelFn, order) {
    const rows = S.breakdown(rides, keyFn);
    if (!rows.length) return;
    rows.sort((a, b) => {
      if (order) {
        const diff = order.indexOf(a.key) - order.indexOf(b.key);
        if (diff) return diff;
      }
      return b.rides - a.rides;
    });

    const section = document.createElement("section");
    section.className = "stats-group";
    const heading = document.createElement("h2");
    heading.textContent = title;
    section.appendChild(heading);

    const table = document.createElement("table");
    table.className = "stats-table";
    table.innerHTML =
      "<thead><tr><th>" +
      escapeHtml(title) +
      "</th><th>" +
      escapeHtml(t("would_again_short", "Would ride again")) +
      "</th><th>" +
      escapeHtml(t("said_no", "said no")) +
      "</th><th>" +
      escapeHtml(t("answers", "answers")) +
      "</th></tr></thead>";
    const body = document.createElement("tbody");
    rows.forEach((row) => {
      const thin = row.rides < DATA.min_sample;
      const tr = document.createElement("tr");
      if (thin) tr.className = "stats-thin";
      tr.appendChild(cell(labelFn ? labelFn(row.key) : String(row.key)));
      tr.appendChild(cell(percent(row.rate) + (row.ci ? " (" + percent(row.ci[0]) + "–" + percent(row.ci[1]) + ")" : "")));
      tr.appendChild(cell(String(row.no)));
      tr.appendChild(cell(String(row.rides) + (thin ? " *" : "")));
      body.appendChild(tr);
    });
    table.appendChild(body);
    section.appendChild(table);
    host.appendChild(section);
  }

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text;
    return td;
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function renderNegatives(host, rides) {
    const counts = new Map();
    rides.forEach((ride) => (ride.n || []).forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1)));
    const section = document.createElement("section");
    section.className = "stats-group";
    const heading = document.createElement("h2");
    heading.textContent = t("what_went_wrong", "What went wrong");
    section.appendChild(heading);
    if (!counts.size) {
      section.appendChild(
        note(
          t(
            "no_negatives",
            "Nobody in this cohort tagged what went wrong. That is an absence of reports, not evidence that nothing happened — the tags only exist on rides answered “no”, and most rides are never reported on at all.",
          ),
        ),
      );
    } else {
      const list = document.createElement("ul");
      list.className = "safety-tags";
      [...counts.entries()]
        .sort((a, b) => b[1] - a[1])
        .forEach(([tag, count]) => {
          const item = document.createElement("li");
          item.textContent = t("neg_" + tag, tag.replace(/_/g, " ")) + " · " + count;
          list.appendChild(item);
        });
      section.appendChild(list);
    }

    // The "no" answers, linked. 30-odd rides in the whole corpus is few enough that a
    // reader can go and read them, and a percentage with no way through to the rides
    // behind it is a claim, not evidence.
    const noRides = rides.filter((ride) => !ride.w && ride.d);
    if (noRides.length) {
      const links = document.createElement("p");
      links.className = "stats-note";
      links.appendChild(document.createTextNode(t("read_the_no", "Read them:") + " "));
      noRides.slice(0, 50).forEach((ride, index) => {
        const link = document.createElement("a");
        link.href = (window.__LANG_PREFIX__ || "") + "/ride/" + encodeURIComponent(ride.d);
        link.textContent = "#" + (index + 1);
        links.appendChild(link);
        if (index < Math.min(noRides.length, 50) - 1) links.appendChild(document.createTextNode(", "));
      });
      section.appendChild(links);
    }
    host.appendChild(section);
  }

  function render() {
    const rides = matching();
    renderHeadline(rides);

    const host = document.getElementById("breakdowns");
    host.innerHTML = "";
    if (!rides.length) return;

    renderBreakdown(host, t("by_driver_gender", "Driver’s gender"), rides, (ride) => ride.dg || "unknown", genderLabel, GENDERS);
    renderBreakdown(host, t("by_driver_age", "Driver’s age"), rides, (ride) => S.band(ride.da, S.AGE_BANDS), bandLabel, S.AGE_BANDS.map((b) => b[2]));
    renderBreakdown(host, t("by_group", "How many were hitchhiking"), rides, (ride) => (ride.p || [[]]).length, (key) => (key === 1 ? t("solo", "Solo") : t("n_people", "{n} hitchhikers").replace("{n}", key)));
    renderBreakdown(host, t("by_hitchhiker_gender", "Hitchhikers’ genders"), rides, (ride) => (ride.p || []).map((person) => person[0] || "unknown"), genderLabel, GENDERS);
    renderBreakdown(host, t("by_daypart", "Time of day"), rides, (ride) => S.daypart(ride.h), (key) => t("daypart_" + key, key), ["morning", "afternoon", "evening", "night"]);
    renderBreakdown(host, t("by_wait", "How long they waited"), rides, (ride) => S.band(ride.wt, S.WAIT_BANDS), bandLabel, S.WAIT_BANDS.map((b) => b[2]));
    renderBreakdown(host, t("by_distance", "How far the ride went"), rides, (ride) => S.band(ride.km, S.DISTANCE_BANDS), bandLabel, S.DISTANCE_BANDS.map((b) => b[2]));
    renderBreakdown(host, t("by_vehicle", "Vehicle"), rides, (ride) => ride.v || null, (key) => t("vehicle_" + key, key));
    renderBreakdown(host, t("by_signal", "How they signalled"), rides, (ride) => ride.s || null, (key) => t("signal_" + key, key));
    renderBreakdown(host, t("by_rating", "Rating they gave the spot"), rides, (ride) => (ride.r == null ? null : ride.r), (key) => "★".repeat(key), [5, 4, 3, 2, 1]);
    renderBreakdown(host, t("by_country", "Country the ride started in"), rides, (ride) => ride.cc || null, countryLabel);
    renderNegatives(host, rides);
  }

  function countryLabel(code) {
    const names = window.__COUNTRY_NAMES__ || {};
    return names[code] || code;
  }

  function bandLabel(key) {
    return t("band_" + key, key);
  }

  // -- boot -----------------------------------------------------------------

  function boot() {
    document.getElementById("add-person").addEventListener("click", () => {
      if (filters.length < MAX_PEOPLE) filters.push(emptyFilter());
      renderPersonCards();
      render();
    });
    const exact = document.getElementById("exact-size");
    exact.addEventListener("change", () => {
      exactSize = exact.checked;
      render();
    });
    renderPersonCards();

    // Root-anchored on purpose: the generated files are served from dist/ by catch_all at
    // the bare path, and this page is also mounted under all 30 /<lang> mirrors.
    fetch("/hitchhiking_safety.json")
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then((data) => {
        DATA = Object.assign(DATA, data);
        render();
      })
      .catch(() => {
        document.getElementById("headline").appendChild(
          note(t("load_failed", "Could not load the ride data. Reload the page to try again.")),
        );
      });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
