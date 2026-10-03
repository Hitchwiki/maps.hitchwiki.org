const test = require("node:test");
const assert = require("node:assert");

const P = require("../hitch/static/push_optin.js");

test("urlBase64ToUint8Array decodes URL-safe base64 with missing padding", () => {
  // "-_8" is the URL-safe form of "+/8=" -> bytes fb ff
  assert.deepStrictEqual(Array.from(P.urlBase64ToUint8Array("-_8")), [0xfb, 0xff]);
  assert.deepStrictEqual(Array.from(P.urlBase64ToUint8Array("AQID")), [1, 2, 3]);
});

test("render does nothing without the opt-in element", () => {
  assert.doesNotThrow(() => P.render());
});
