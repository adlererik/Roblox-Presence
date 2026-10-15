const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {codeFromText, validCookie, saveCredential, verifyObserver} = require('../tools/quick_login.cjs');

test('Extract only the displayed code in the official Option 2 section', () => {
  assert.equal(codeFromText('Quick Sign In Code\nOption 2\nAB12CD\nOpen your Roblox app'), 'AB12CD');
  for (const text of ['Another value ABC123', 'Option 2\nABC1234', 'Option 2\n'])
    assert.throws(() => codeFromText(text));
});
test('Require the intended observer before saving any credential', () => {
  verifyObserver({id: 11}, 11);
  for (const identity of [{id: 22}, {}, {id: '11'}, null])
    assert.throws(() => verifyObserver(identity, 11), /observer_mismatch/);
});
test('Reject credential header injection or malformed values', () => {
  assert.equal(validCookie('TEST_OBSERVER_SESSION'), true);
  for (const value of ['', 'bad value', 'bad;value', 'bad\nvalue', 'bad"value', 'x'.repeat(16385)])
    assert.equal(validCookie(value), false);
});
test('Atomically save a private credential and preserve it on validation failure', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'presence-authorization-test-'));
  try {
    const target = path.join(directory, 'cookie');
    saveCredential(target, 'TEST_FIRST_SESSION');
    assert.equal(fs.statSync(target).mode & 0o777, 0o600);
    assert.throws(() => saveCredential(target, 'bad;value'));
    assert.equal(fs.readFileSync(target, 'utf8'), 'TEST_FIRST_SESSION\n');
    saveCredential(target, 'TEST_NEW_SESSION');
    assert.equal(fs.readFileSync(target, 'utf8'), 'TEST_NEW_SESSION\n');
    assert.deepEqual(fs.readdirSync(directory), ['cookie']);
  } finally { fs.rmSync(directory, {recursive: true}); }
});
