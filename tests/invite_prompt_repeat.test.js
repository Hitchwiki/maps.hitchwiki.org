const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "hitch", "static", "map.js"),
  "utf8",
);

// Pull the two prompt-memory helpers plus the key constants out of map.js and
// run them against a fake localStorage, the same way signup_prompt_attribution
// extracts and executes its block.
function helpers(store) {
  const keysStart = SOURCE.indexOf("const SIGNUP_PROMPT_SEEN_KEY");
  const fnStart = SOURCE.indexOf("function promptSeen(");
  const markStart = SOURCE.indexOf("function markPromptSeen(");
  const catchEmpty =
    SOURCE.indexOf("} catch (e) {}", markStart) + "} catch (e) {}".length;
  const fnEnd = SOURCE.indexOf("}", catchEmpty) + 1;
  assert.ok(
    keysStart !== -1 &&
      fnStart > keysStart &&
      fnEnd > fnStart &&
      markStart > fnStart,
    "prompt-memory block moved",
  );
  const block =
    SOURCE.slice(
      keysStart,
      SOURCE.indexOf("\n", SOURCE.indexOf("INVITE_PROMPT_MAX_AGE_DAYS = 90")),
    ) +
    "\n" +
    SOURCE.slice(fnStart, fnEnd) +
    "\nreturn { promptSeen, markPromptSeen, INVITE_PROMPT_SEEN_KEY, SIGNUP_PROMPT_SEEN_KEY, INVITE_PROMPT_MAX_AGE_DAYS };";
  const localStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => {
      store[k] = String(v);
    },
  };
  return new Function("localStorage", "Date", block)(localStorage, Date);
}

test("the invite prompt returns after 90 days, unlike the permanent anon marker", () => {
  const store = {};
  const h = helpers(store);

  assert.strictEqual(
    h.promptSeen(h.INVITE_PROMPT_SEEN_KEY, h.INVITE_PROMPT_MAX_AGE_DAYS),
    false,
  );
  h.markPromptSeen(h.INVITE_PROMPT_SEEN_KEY);
  assert.strictEqual(
    h.promptSeen(h.INVITE_PROMPT_SEEN_KEY, h.INVITE_PROMPT_MAX_AGE_DAYS),
    true,
  );

  // Rewind the stored stamp past the window.
  store[h.INVITE_PROMPT_SEEN_KEY] = String(Date.now() - 91 * 86400000);
  assert.strictEqual(
    h.promptSeen(h.INVITE_PROMPT_SEEN_KEY, h.INVITE_PROMPT_MAX_AGE_DAYS),
    false,
  );

  // 89 days is still inside the window.
  store[h.INVITE_PROMPT_SEEN_KEY] = String(Date.now() - 89 * 86400000);
  assert.strictEqual(
    h.promptSeen(h.INVITE_PROMPT_SEEN_KEY, h.INVITE_PROMPT_MAX_AGE_DAYS),
    true,
  );
});

test("the anon sign-up marker stays permanent (no maxAgeDays)", () => {
  const store = {};
  const h = helpers(store);
  h.markPromptSeen(h.SIGNUP_PROMPT_SEEN_KEY);
  store[h.SIGNUP_PROMPT_SEEN_KEY] = String(Date.now() - 999 * 86400000);
  assert.strictEqual(h.promptSeen(h.SIGNUP_PROMPT_SEEN_KEY), true);
});

test('a legacy "1" marker counts as seen for both prompts', () => {
  const store = { [`invitePromptSeen`]: "1", [`signupPromptSeen`]: "1" };
  const h = helpers(store);
  assert.strictEqual(
    h.promptSeen(h.INVITE_PROMPT_SEEN_KEY, h.INVITE_PROMPT_MAX_AGE_DAYS),
    true,
  );
  assert.strictEqual(h.promptSeen(h.SIGNUP_PROMPT_SEEN_KEY), true);
});
