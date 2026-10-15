/* Optional one-time authorization through Roblox's normal web UI.
 * Requires Node.js and Playwright only for setup, not for the running monitor.
 * The operator approves the code in Roblox: More Page > Quick Sign In.
 * Never emits or stores browser history, other cookies, or private login keys.
 */
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

function codeFromText(text) {
  const match = text.match(/Option 2\s+([A-Z0-9]{6})\b/);
  if (!match) throw new Error('quick_signin_code_not_found');
  return match[1];
}

function validCookie(value) {
  return typeof value === 'string' && value.length > 0 && value.length <= 16384
    && /^[\x21-\x7e]+$/.test(value) && !/[;,\"]/.test(value);
}

function saveCredential(filename, value) {
  if (!path.isAbsolute(filename) || !validCookie(value)) throw new Error('invalid_session_destination_or_value');
  const temp = path.join(path.dirname(filename), '.' + path.basename(filename) + '.' + crypto.randomUUID());
  let fd;
  try {
    fd = fs.openSync(temp, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
    fs.writeFileSync(fd, value + '\n');
    fs.fsyncSync(fd);
    fs.closeSync(fd); fd = undefined;
    fs.renameSync(temp, filename);
    const directory = fs.openSync(path.dirname(filename), fs.constants.O_RDONLY | fs.constants.O_DIRECTORY);
    try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); }
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
    if (fs.existsSync(temp)) fs.unlinkSync(temp);
  }
}

function verifyObserver(identity, expected) {
  if (!identity || !Number.isSafeInteger(identity.id) || identity.id !== expected)
    throw new Error('roblox_observer_mismatch');
}

async function main() {
  process.umask(0o077);
  if (process.argv.length !== 4) throw new Error('provide_config_and_status_file');
  const config = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const statusFile = path.resolve(process.argv[3]);
  if (!Number.isSafeInteger(config.observer_user_id) || config.observer_user_id <= 0
      || typeof config.cookie_file !== 'string' || !path.isAbsolute(config.cookie_file))
    throw new Error('invalid_local_authorization_configuration');
  if (fs.existsSync(statusFile)) throw new Error('authorization_status_already_exists');
  function status(data) {
    const temp = statusFile + '.new';
    fs.writeFileSync(temp, JSON.stringify(data), {mode: 0o600, flag: 'wx'});
    fs.renameSync(temp, statusFile);
  }
  const {chromium} = require('playwright');
  let browser;
  try {
    status({phase: 'opening_official_login'});
    browser = await chromium.launch({headless: true, chromiumSandbox: true,
      args: ['--disable-dev-shm-usage'], timeout: 20000});
    const context = await browser.newContext();
    const page = await context.newPage();
    const response = await page.goto('https://www.roblox.com/login',
      {waitUntil: 'domcontentloaded', timeout: 30000});
    if (!response || response.status() !== 200) throw new Error('official_login_page_unavailable');
    const decline = page.getByRole('button', {name: 'Decline All', exact: true});
    try {
      await decline.waitFor({state: 'visible', timeout: 10000});
      await decline.click();
      await page.locator('.cookie-banner-bg').waitFor({state: 'hidden', timeout: 10000});
    } catch (error) {
      if (error.name !== 'TimeoutError') throw new Error('cookie_preference_failed');
    }
    await page.getByRole('button', {name: /^Quick Sign-in$|^Log In with Another Device$/}).click({timeout: 15000});
    await page.getByText('Option 2', {exact: true}).waitFor({state: 'visible', timeout: 15000});
    const code = codeFromText(await page.locator('body').innerText());
    // Stop before the native page could refresh its first code; no retry loop.
    const expires = Date.now() + 280000;
    status({phase: 'waiting_for_phone', code, expires_at: Math.floor(expires / 1000),
      approval_location: 'Roblox More Page > Quick Sign In', full_account_access: true});
    while (Date.now() < expires) {
      const current = (await context.cookies('https://users.roblox.com')).find(c => c.name === '.ROBLOSECURITY');
      if (current && current.value) {
        // Stop page traffic before reading the final, possibly rotated credential.
        await page.close();
        const identityResponse = await context.request.get('https://users.roblox.com/v1/users/authenticated',
          {timeout: 8000, maxRedirects: 0});
        if (identityResponse.status() !== 200) throw new Error('roblox_authentication_failed');
        verifyObserver(await identityResponse.json(), config.observer_user_id);
        const cookie = (await context.cookies('https://users.roblox.com')).find(c => c.name === '.ROBLOSECURITY');
        if (!cookie || !validCookie(cookie.value)) throw new Error('roblox_session_missing');
        saveCredential(config.cookie_file, cookie.value);
        status({phase: 'authorized', observer_verified: true, credential_saved: true});
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    status({phase: 'expired', credential_saved: false});
  } catch (error) {
    const allowed = ['roblox_observer_mismatch', 'roblox_authentication_failed',
      'roblox_session_missing', 'official_login_page_unavailable', 'quick_signin_code_not_found'];
    status({phase: 'failed', error: allowed.includes(error.message) ? error.message : 'authorization_flow_failed', credential_saved: false});
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
  }
}

module.exports = {codeFromText, validCookie, saveCredential, verifyObserver};
if (require.main === module) main().catch(() => {
  // No exception text, browser cookies, page bodies, or network URLs reach logs.
  process.stderr.write('Authorization setup failed; no credential was displayed.\n');
  process.exitCode = 1;
});
