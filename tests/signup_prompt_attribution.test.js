const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(path.join(__dirname, "..", "hitch", "static", "map.js"), "utf8");

function attributionBlock() {
  const start = SOURCE.indexOf("function trackSignupPromptAccountCreated()");
  const call = SOURCE.indexOf("trackSignupPromptAccountCreated();", start);
  assert.ok(start !== -1 && call > start, "signup attribution block moved or disappeared");
  return SOURCE.slice(start, call + "trackSignupPromptAccountCreated();".length);
}

function runAt(url) {
  const events = [];
  const replacements = [];
  const window = {
    location: { href: url },
    history: {
      replaceState(_state, _title, target) {
        replacements.push(target);
      },
    },
  };
  const execute = new Function("window", "logSignupPrompt", "URL", attributionBlock());
  execute(window, (prompt, action) => events.push([prompt, action]), URL);
  return { events, replacements };
}

test("an attributed new account records once and removes only its marker", () => {
  const result = runAt(
    "https://maps.hitchwiki.org/?welcome=1&signup_prompt=account-created#map=4/50/10",
  );
  assert.deepStrictEqual(result.events, [["anon-signup", "account-created"]]);
  assert.deepStrictEqual(result.replacements, ["/?welcome=1#map=4/50/10"]);
});

test("an existing user logging in through the prompt records as a distinct outcome, not lost", () => {
  const result = runAt("https://maps.hitchwiki.org/?signup_prompt=logged-in#map=4/50/10");
  assert.deepStrictEqual(result.events, [["anon-signup", "logged-in"]]);
  assert.deepStrictEqual(result.replacements, ["/#map=4/50/10"]);
});

test("ordinary and forged attribution values record nothing", () => {
  assert.deepStrictEqual(runAt("https://maps.hitchwiki.org/?welcome=1"), {
    events: [],
    replacements: [],
  });
  assert.deepStrictEqual(runAt("https://maps.hitchwiki.org/?signup_prompt=made-up"), {
    events: [],
    replacements: [],
  });
});

test("the anonymous prompt carries its allowlisted source into login", () => {
  assert.match(SOURCE, /window\.location\.href = "\/login\?source=anon-signup";/);
});
