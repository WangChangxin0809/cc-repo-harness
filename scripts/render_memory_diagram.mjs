#!/usr/bin/env node
// Generate the shared-memory diagram with the unmodified Archify v2.16.0 package.
// See docs/reference/diagram-gallery.md#reproduce-the-shared-memory-diagram.
import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
if (args.includes('--help')) {
  console.log('Usage: node scripts/render_memory_diagram.mjs [--archify <extracted archify directory>]');
  process.exit(0);
}
if (args.length && (args.length !== 2 || args[0] !== '--archify')) {
  throw new Error('Expected --archify <directory>; see --help.');
}
const tool = path.resolve(args[1] || path.join(root, 'tmp/shared-memory-implementation/archify-v2.16.0/archify'));
const work = path.join(root, 'tmp/shared-memory-implementation');
const stem = '07-shared-memory.architecture';
const source = path.join(root, '.github/assets/diagrams', `${stem}.json`);
const html = path.join(work, `${stem}.html`);
const svg = path.join(root, '.github/assets/diagrams', `${stem}.svg`);
const pkg = JSON.parse(fs.readFileSync(path.join(tool, 'package.json'), 'utf8'));
if (pkg.version !== '2.16.0') throw new Error(`Expected Archify 2.16.0, found ${pkg.version}.`);
fs.mkdirSync(work, { recursive: true });
const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');

function cli(command, ...rest) {
  const result = spawnSync(process.execPath, [path.join(tool, 'bin/archify.mjs'), command, ...rest], {
    cwd: root,
    encoding: 'utf8',
    windowsHide: true,
    env: { ...process.env, ARCHIFY_UPDATE_CHECK_DISABLED: '1' },
  });
  if (result.error) throw result.error;
  fs.writeFileSync(path.join(work, `archify-${command}.json`), result.stdout);
  if (result.status !== 0) throw new Error(result.stderr || result.stdout || `${command} failed`);
  return JSON.parse(result.stdout);
}

const validation = cli('validate', 'architecture', source, '--quality', 'showcase', '--json');
const delivery = cli('deliver', 'architecture', source, html, '--quality', 'showcase', '--json');
const { ChromeVisualBrowser, findChrome, runVisualCheck } = await import(
  pathToFileURL(path.join(tool, 'bin/visual-check.mjs')).href
);

// v2.16.0 optionally requests Google Fonts. Block remote subresources before
// opening the local artifact; no repository material leaves this process.
async function offlineBrowser(executable) {
  const browser = new ChromeVisualBrowser(executable, {
    spawnImpl: (command, options, settings) => spawn(command,
      [...options, '--host-resolver-rules=MAP * ~NOTFOUND'],
      { ...settings, windowsHide: true }),
  });
  try {
    const session = await browser.sessionPromise;
    await browser.cdp.send('Network.enable', {}, session);
    await browser.cdp.send('Network.setBlockedURLs', { urls: ['http://*', 'https://*'] }, session);
    return browser;
  } catch (error) {
    await browser.close();
    throw error;
  }
}

// The same official implementation used by `archify visual-check`, with only
// the supported browserFactory seam adding network isolation and hidden launch.
const check = await runVisualCheck({ artifactPath: html, browserFactory: offlineBrowser });
if (check.exitCode !== 0) throw new Error(`Archify visual-check: ${check.receipt.status}`);
const chrome = findChrome();
if (!chrome) throw new Error('Chrome/Chromium is required; set ARCHIFY_CHROME to its executable.');
const browser = await offlineBrowser(chrome);
let exported;
try {
  await browser.inspect({ artifactPath: html, width: 1440, height: 900, theme: 'light' });
  const session = await browser.sessionPromise;
  const response = await browser.cdp.send('Runtime.evaluate', {
    awaitPromise: true,
    returnByValue: true,
    expression: `(async () => {
      // Capture the exact Blob made by Archify's official export menu.
      const original = URL.createObjectURL;
      let blob;
      URL.createObjectURL = function (value) { blob = value; return original.call(URL, value); };
      try {
        await Archify.exportMenu.run('svg');
        const page = document.documentElement;
        if (!blob || page.getAttribute('data-last-export-format') !== 'svg' ||
            page.getAttribute('data-last-export-canonical') !== 'true') {
          throw new Error(page.getAttribute('data-last-export-error') || 'Canonical SVG export failed.');
        }
        return { text: await blob.text(), bytes: blob.size, canonical: true };
      } finally { URL.createObjectURL = original; }
    })()`,
  }, session);
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text);
  exported = response.result.value;
  if (!exported?.text?.startsWith('<svg') || Buffer.byteLength(exported.text) !== exported.bytes) {
    throw new Error('The official export did not produce the expected SVG bytes.');
  }
  fs.writeFileSync(svg, exported.text);

  // Inspect the exact exported image, independently of the HTML viewer.
  for (const theme of ['light', 'dark']) {
    await browser.cdp.send('Emulation.setEmulatedMedia', {
      features: [{ name: 'prefers-color-scheme', value: theme }],
    }, session);
    const loaded = browser.cdp.waitFor('Page.loadEventFired', session);
    await browser.cdp.send('Page.navigate', { url: pathToFileURL(svg).href }, session);
    await loaded;
    const screenshot = await browser.cdp.send('Page.captureScreenshot', { format: 'png' }, session);
    fs.writeFileSync(path.join(work, `${stem}.export.${theme}.png`), Buffer.from(screenshot.data, 'base64'));
  }
} finally {
  await browser.close();
}

const receipt = {
  generator: 'Archify 2.16.0',
  release: 'https://github.com/tt-a1i/archify/releases/tag/v2.16.0',
  archiveSha256: '4c59fa6557a2385beaaef8c7219cc414573acc9f0c30a932d5053b0b20689a46',
  specification: delivery.specification,
  artifact: delivery.artifact,
  validation: delivery.validation,
  browserEvidence: check.receipt.status,
  visualReview: 'pending; inspect the HTML and exported-image screenshots',
  svg: { sha256: digest(fs.readFileSync(svg)), bytes: exported.bytes, canonical: exported.canonical },
};
fs.writeFileSync(path.join(work, 'archify-export.json'), `${JSON.stringify(receipt, null, 2)}\n`);
console.log(JSON.stringify({ ...receipt, paths: { html, svg } }, null, 2));
if (!validation.ok) process.exitCode = 1;
