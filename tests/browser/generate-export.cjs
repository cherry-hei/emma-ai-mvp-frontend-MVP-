const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, '.codex-temp/browser-evidence');
fs.mkdirSync(output, { recursive: true });
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ acceptDownloads: true, locale: 'en-US', viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(20000);
  const report = { checks: [], errors: [], requests: [], blockedExternal: [] };
  page.on('pageerror', e => report.errors.push(e.message));
  page.on('response', r => { if (r.url().startsWith('http://127.0.0.1:8017')) report.requests.push({ method: r.request().method(), url: r.url(), status: r.status() }); });
  await context.route('**/*', route => {
    const u = new URL(route.request().url());
    if (u.hostname === '127.0.0.1' && ['3017', '8017'].includes(u.port)) return route.continue();
    report.blockedExternal.push(route.request().url());
    return route.abort();
  });
  try {
    // Invented identity only; this is file-transfer acceptance, not live login/RLS.
    await context.addInitScript(() => {
      localStorage.setItem('emma_token','local-synthetic-test-token');
      localStorage.setItem('emma_session',JSON.stringify({user_id:'owner1',email:'owner@example.invalid',role:'OWNER',facility_id:'f1',facility_name:'Invented browser test home'}));
    });
    await page.goto('http://127.0.0.1:3017/roster', { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.getByRole('button', { name: 'Analysis settings', exact: true }).click();
    const section = page.getByRole('region', { name: 'Facility analysis settings' });
    await section.locator('input[type=file]').setInputFiles(path.join(root, 'docs/naac/roster-analysis.synthetic.json'));
    await section.getByText('6 codes · 1 roles · 1 demand rows', { exact: true }).waitFor();
    assert.equal(await section.getByRole('button', { name: 'Confirm and save version' }).isEnabled(), false);
    report.checks.push('JSON upload displays exact code/role/demand counts; confirmation required');
    await section.getByRole('checkbox').check();
    const savePromise = page.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/facility-configs'));
    await section.getByRole('button', { name: 'Confirm and save version' }).click();
    const save = await savePromise;
    assert.equal(save.status(), 201);
    report.savedConfig = await save.json();
    assert.equal(report.savedConfig.config_json.status, 'confirmed');
    assert.equal(await page.getByRole('combobox', { name: 'Generate from' }).inputValue(), report.savedConfig.id);
    report.checks.push('UI confirmation saves and selects new configuration version');
    const jobPromise = page.waitForResponse(async r => r.url().includes('/optimization-jobs/') && r.status()===200 && (await r.json()).status==='completed', {timeout:60000});
    await page.getByRole('button', { name: 'Generate roster options', exact: true }).click();
    report.job = await (await jobPromise).json();
    await page.getByRole('button', { name: /^C draft/ }).waitFor({ timeout: 60000 });
    assert.equal(await page.getByRole('button', { name: /^[ABC] draft/ }).count(), 3);
    report.checks.push('Actual CP-SAT produces A/B/C drafts');
    await page.getByRole('button', { name: '✕', exact: true }).click();
    await page.getByRole('button', { name: /^C draft/ }).click();
    const button = page.getByRole('button', { name: /Export Roster/ });
    await button.waitFor();
    const exportResponse = page.waitForResponse(r => r.url().includes('/exports/naac/tahduty.xlsx'));
    const downloadPromise = page.waitForEvent('download');
    await button.click();
    const [response, download] = await Promise.all([exportResponse, downloadPromise]);
    assert.equal(response.status(), 200);
    assert.equal(await download.failure(), null);
    report.exportUrl = response.url();
    const responseBytes = await response.body();
    fs.writeFileSync(path.join(output, 'response.xlsx'), responseBytes);
    report.exportSha256 = require('node:crypto').createHash('sha256').update(responseBytes).digest('hex');
    assert.equal(new URL(report.exportUrl).searchParams.get('version_id'), report.job.result_json.roster_options.find(o=>o.plan_mode==='C').roster_version_id);
    report.filename = download.suggestedFilename();
    const savedPath = path.join(output, report.filename);
    await download.saveAs(savedPath);
    report.bytes = fs.statSync(savedPath).size;
    assert.ok(report.bytes > 0);
    report.checks.push('Selected-version export downloads a nonempty XLSX to disk');
    await page.screenshot({ path: path.join(output, 'selected-version.png'), fullPage: true });
    assert.deepEqual(report.errors, []);
    report.checks.push('No browser JavaScript errors');
    report.status = 'passed';
  } catch (e) {
    report.status = 'failed'; report.failure = e.stack; report.pageUrl = page.url();
    fs.writeFileSync(path.join(output, 'failure-ui.txt'), await page.locator('body').innerText());
    await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
    process.exitCode = 1;
  } finally {
    await browser.close();
    if (report.status === 'passed') assert.equal(fs.readFileSync(path.join(output, report.filename)).subarray(0, 4).toString('hex'), '504b0304');
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ status: report.status, checks: report.checks, failure: report.failure, bytes: report.bytes }, null, 2));
  }
})();
