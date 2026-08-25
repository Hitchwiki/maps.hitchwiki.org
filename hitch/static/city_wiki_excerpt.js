// Client-side Hitchwiki excerpt for a city page (/city/<country>/<city>.html).
//
// Mirrors map.js's loadCountrySheetLead / renderCountryWikitext: the Hitchwiki
// API sits behind Cloudflare's bot challenge, which blocks requests from this
// host's own datacenter IP but lets a real visitor's browser through -- so the
// fetch has to happen here, in the browser, not in cities.py at build time.
// That also sidesteps the batch-fetch-at-build-time risk (27k+ pages x up to 31
// languages hitting Cloudflare's challenge, no caching strategy) a server-side
// version would have carried -- this fetches one article, once, per pageview.
//
// Kept as its own file rather than reusing map.js's country-sheet functions:
// city pages don't load map.js (no Leaflet, no map shell here), and this is a
// small, self-contained transform that doesn't need the rest of it.
(function () {
  var WIKI_BASE = "https://hitchwiki.org/en/";

  function escapeHtmlCW(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function wikiLink(target) {
    var page = target.trim().replace(/ /g, "_");
    return WIKI_BASE + encodeURI(page).replace(/"/g, "%22");
  }

  // Remove {{...}} templates, honouring nesting.
  function stripTemplates(text) {
    var out = "",
      depth = 0;
    for (var i = 0; i < text.length; i++) {
      if (text[i] === "{" && text[i + 1] === "{") {
        depth++;
        i++;
        continue;
      }
      if (text[i] === "}" && text[i + 1] === "}" && depth > 0) {
        depth--;
        i++;
        continue;
      }
      if (depth === 0) out += text[i];
    }
    return out;
  }

  // Remove [[File:...]] / [[Image:...]] embeds, honouring nested [[ ]] (a regex
  // can't do this reliably -- see map.js's stripWikiImages for why).
  function stripImages(text) {
    var out = "";
    for (var i = 0; i < text.length; ) {
      if (text[i] === "[" && text[i + 1] === "[" && /^(?:File|Image):/i.test(text.slice(i + 2))) {
        var depth = 1;
        i += 2;
        while (i < text.length && depth > 0) {
          if (text[i] === "[" && text[i + 1] === "[") {
            depth++;
            i += 2;
          } else if (text[i] === "]" && text[i + 1] === "]") {
            depth--;
            i += 2;
          } else i++;
        }
        continue;
      }
      out += text[i];
      i++;
    }
    return out;
  }

  // Render lead-section wikitext as safe HTML (prose + links only). Same
  // transform as map.js's renderCountryWikitext, minus the "drop the redundant
  // top-level heading" special case -- city articles don't repeat the page
  // title as a heading the way country "Hitchhiking" sections do.
  //
  // `title` fills in MediaWiki's self-reference magic words -- confirmed live
  // against Hitchwiki's actual Berlin article, which opens "'''{{FULLPAGENAME}}'''
  // is the capital of Germany": stripping templates blindly (as the generic
  // {{...}} removal below has to, for infoboxes) would delete the subject of
  // the sentence and leave orphaned '' '' quote markers. Paris/Munich spell
  // the name out literally, so this only fires when an article actually uses
  // the magic word -- but nothing rules out more of the 27k+ city articles
  // doing the same.
  function renderExcerpt(raw, title) {
    var t = raw;
    if (title) {
      t = t.replace(/\{\{\s*(?:FULLPAGENAME|PAGENAME|BASEPAGENAME)\s*\}\}/gi, title);
    }
    t = t.replace(/<!--[\s\S]*?-->/g, "");
    t = t.replace(/<ref[^>]*\/>/gi, "");
    t = t.replace(/<ref[^>]*>[\s\S]*?<\/ref>/gi, "");
    t = t.replace(/<gallery[^>]*>[\s\S]*?<\/gallery>/gi, "");
    // Stray raw HTML tags (e.g. Berlin's real article opens with a bare "<br>"
    // before its infobox, confirmed live) would otherwise survive into the
    // escape step below and print as literal "&lt;br&gt;" text, or worse,
    // form their own empty paragraph. <br> becomes a line break (it's doing
    // real formatting work); anything else is just dropped -- this renderer
    // only ever emits its own <p>/<h4>/<a>/<strong>/<em> tags, never wiki-
    // authored markup verbatim.
    t = t.replace(/<br\s*\/?>/gi, "\n");
    t = t.replace(/<\/?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?>/g, "");
    t = stripTemplates(t);
    t = t.replace(/__[A-Z]+__/g, "");
    t = stripImages(t);
    t = t.replace(/^\s*[*#:;].*$/gm, "");

    t = t
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

    t = t.replace(/\[\[([^\[\]|]+)\|([^\[\]]+)\]\]/g, function (m, target, label) {
      return '<a href="' + wikiLink(target) + '" target="_blank" rel="noopener">' + label + "</a>";
    });
    t = t.replace(/\[\[([^\[\]]+)\]\]/g, function (m, target) {
      return '<a href="' + wikiLink(target) + '" target="_blank" rel="noopener">' + target + "</a>";
    });
    t = t.replace(/\[(https?:\/\/[^\s\]]+)\s+([^\]]+)\]/g, function (m, url, label) {
      return '<a href="' + encodeURI(url) + '" target="_blank" rel="noopener">' + label + "</a>";
    });
    t = t.replace(/\[(https?:\/\/[^\s\]]+)\]/g, function (m, url) {
      return '<a href="' + encodeURI(url) + '" target="_blank" rel="noopener">' + escapeHtmlCW(url) + "</a>";
    });
    t = t.replace(/'''(.+?)'''/g, "<strong>$1</strong>");
    t = t.replace(/''(.+?)''/g, "<em>$1</em>");

    var out = [];
    t.split(/\n{2,}/).forEach(function (block) {
      var para = [];
      function flush() {
        var text = para.join(" ").trim();
        if (text) out.push("<p>" + text + "</p>");
        para = [];
      }
      block.split("\n").forEach(function (line) {
        var heading = line.trim().match(/^={2,6}\s*(.+?)\s*={2,6}$/);
        if (heading) {
          flush();
          out.push("<h4>" + heading[1].trim() + "</h4>");
        } else {
          para.push(line);
        }
      });
      flush();
    });
    return out.join("");
  }

  function wikiApi(title, params) {
    return (
      WIKI_BASE +
      "api.php?action=parse&redirects=1&format=json&origin=*" +
      params +
      "&page=" +
      encodeURIComponent(title)
    );
  }

  // Exposed for the node test (tests/city_wiki_excerpt.test.js) -- harmless in
  // the browser, same pattern as this codebase's other window.* exposures.
  window.__cityWikiExcerpt = { renderExcerpt: renderExcerpt, wikiLink: wikiLink };

  function init() {
    var container = document.getElementById("city-wiki-excerpt");
    if (!container) return;
    var title = container.getAttribute("data-title");
    if (!title) return;
    fetch(wikiApi(title, "&prop=wikitext&section=0"))
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        // No article, a disambiguation page, or a redlink: stay hidden rather
        // than show an error -- ~596 of 27,188 cities have no article at all,
        // and that is an expected, not exceptional, outcome here.
        if (!data || data.error || !data.parse) return;
        var wikitext = data.parse.wikitext && data.parse.wikitext["*"];
        if (!wikitext) return;
        var html = renderExcerpt(wikitext, title);
        if (!html) return;
        var wikiUrl = wikiLink(title);
        container.innerHTML =
          '<div class="city-wiki-excerpt-text">' +
          html +
          "</div>" +
          '<p class="city-wiki-excerpt-source">Text from <a href="' +
          wikiUrl +
          '" target="_blank" rel="noopener">Hitchwiki: ' +
          escapeHtmlCW(title) +
          '</a>, licensed <a href="https://creativecommons.org/licenses/by-sa/3.0/" target="_blank" rel="noopener">CC BY-SA</a>.</p>';
        if (window.hmTrack) window.hmTrack("city_wiki_excerpt_shown", {});
      })
      .catch(function () {
        /* stay hidden, matching the country sheet's degrade-quietly rule */
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
