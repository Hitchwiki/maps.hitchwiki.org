// Issue #351: the stops input offers Photon place suggestions that store "lat, lon name".
const fs = require('fs');
const assert = require('assert');
const src = fs.readFileSync(__dirname + '/../hitch/templates/ride_form.html', 'utf8');
assert(/initFreeTextTags\(\{ inputId, tagsId, hiddenId, maxTags, suggest \}\)/.test(src), 'suggest option');
assert(/photon\.komoot\.io\/api\/\?limit=5&q=/.test(src), 'photon lookup');
assert(/c\[1\]\.toFixed\(5\) \+ ', ' \+ c\[0\]\.toFixed\(5\) \+ ' ' \+ pr\.name/.test(src), 'lat, lon name format');
assert(/addEventListener\('mousedown'/.test(src), 'mousedown to beat blur');
assert(/ride-stop-input[^}]*suggest: true/s.test(src), 'enabled for stops');
console.log('ok');
// #412: Enter on a name equal to the top suggestion stores the located stop.
assert(/topSuggestion\.name\.toLowerCase\(\) === label\.toLowerCase\(\)/.test(src), 'exact-match auto-locate');
console.log('ok 412');
