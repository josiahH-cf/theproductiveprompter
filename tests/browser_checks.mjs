#!/usr/bin/env node

/**
 * Dependency-free browser behavior checks for the static site.
 *
 * Usage:
 *   node tests/browser_checks.mjs --root <repository> --json
 *
 * The harness deliberately uses only Node built-ins and Chrome/Edge's DevTools
 * protocol.  It serves the repository from an ephemeral loopback origin so
 * root-relative links, form validation, responsive layout, and new-tab behavior are real.
 */

import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, readFile, readdir, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, extname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const EMAIL = 'josiah.hunter.it@gmail.com';
const TIMEOUT_MS = 12_000;

function parseArgs(argv) {
  const options = { root: resolve(dirname(fileURLToPath(import.meta.url)), '..'), json: false };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--json') options.json = true;
    else if (argv[index] === '--root' && argv[index + 1]) options.root = resolve(argv[++index]);
    else throw new Error(`Unknown or incomplete argument: ${argv[index]}`);
  }
  return options;
}

function mimeType(pathname) {
  return ({
    '.css': 'text/css; charset=utf-8',
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.md': 'text/markdown; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.xml': 'application/xml; charset=utf-8',
  })[extname(pathname).toLowerCase()] || 'application/octet-stream';
}

async function startSiteServer(root) {
  const server = createServer(async (request, response) => {
    try {
      const url = new URL(request.url || '/', 'http://127.0.0.1');
      let pathname = decodeURIComponent(url.pathname);
      if (pathname === '/') pathname = '/index.html';
      const diskPath = resolve(root, `.${pathname}`);
      const outside = relative(root, diskPath).startsWith(`..${sep}`) || relative(root, diskPath) === '..';
      if (outside) {
        response.writeHead(403).end('Forbidden');
        return;
      }
      if ((await stat(diskPath)).isDirectory()) {
        response.writeHead(404).end('Not Found');
        return;
      }
      const body = await readFile(diskPath);
      const type = mimeType(diskPath);
      response.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' }).end(body);
    } catch (error) {
      response.writeHead(error?.code === 'ENOENT' ? 404 : 500).end(error?.code === 'ENOENT' ? 'Not Found' : 'Server error');
    }
  });
  await new Promise((accept, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', accept);
  });
  const address = server.address();
  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    close: () => new Promise((accept) => server.close(accept)),
  };
}

async function firstExisting(paths) {
  for (const candidate of paths.filter(Boolean)) {
    try {
      if ((await stat(candidate)).isFile()) return candidate;
    } catch { /* keep looking */ }
  }
  return null;
}

async function discoverBrowser() {
  const env = process.env;
  const candidates = [env.CHROME_PATH, env.BROWSER_PATH];
  if (process.platform === 'win32') {
    candidates.push(
      env.ProgramFiles && join(env.ProgramFiles, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      env['ProgramFiles(x86)'] && join(env['ProgramFiles(x86)'], 'Google', 'Chrome', 'Application', 'chrome.exe'),
      env.LOCALAPPDATA && join(env.LOCALAPPDATA, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      env.ProgramFiles && join(env.ProgramFiles, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      env['ProgramFiles(x86)'] && join(env['ProgramFiles(x86)'], 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    );
  } else if (process.platform === 'darwin') {
    candidates.push(
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    );
  } else {
    candidates.push('/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/microsoft-edge');
  }
  return firstExisting(candidates);
}

async function launchBrowser(executable) {
  const profile = await mkdtemp(join(tmpdir(), 'tpp-browser-checks-'));
  const child = spawn(executable, [
    '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
    '--disable-component-update', '--disable-default-apps', '--disable-sync',
    '--disable-dev-shm-usage', '--no-sandbox', '--window-size=1280,900', 'about:blank',
  ], { stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });

  let diagnostic = '';
  const endpoint = await new Promise((accept, reject) => {
    const timer = setTimeout(() => reject(new Error(`Browser did not expose DevTools. ${diagnostic.slice(-500)}`)), TIMEOUT_MS);
    const inspect = (chunk) => {
      diagnostic += chunk.toString();
      const match = diagnostic.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {
        clearTimeout(timer);
        accept(match[1]);
      }
    };
    child.stdout.on('data', inspect);
    child.stderr.on('data', inspect);
    child.once('error', (error) => { clearTimeout(timer); reject(error); });
    child.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Browser exited early (${code}). ${diagnostic.slice(-500)}`)); });
  });
  const port = Number(new URL(endpoint).port);
  return {
    child,
    port,
    profile,
    async close() {
      if (!child.killed) child.kill();
      await new Promise((accept) => child.once('exit', accept)).catch(() => {});
      await rm(profile, { recursive: true, force: true }).catch(() => {});
    },
  };
}

async function jsonEndpoint(port, pathname, options = {}) {
  const response = await fetch(`http://127.0.0.1:${port}${pathname}`, options);
  if (!response.ok) throw new Error(`DevTools endpoint ${pathname} returned ${response.status}`);
  return response.json();
}

class CdpClient {
  constructor(url) {
    this.url = url;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    this.socket = new WebSocket(this.url);
    await new Promise((accept, reject) => {
      const timer = setTimeout(() => reject(new Error('Timed out opening DevTools WebSocket')), TIMEOUT_MS);
      this.socket.addEventListener('open', () => { clearTimeout(timer); accept(); }, { once: true });
      this.socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Could not open DevTools WebSocket')); }, { once: true });
    });
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(typeof event.data === 'string' ? event.data : Buffer.from(event.data).toString());
      if (message.id) {
        const pending = this.pending.get(message.id);
        if (!pending) return;
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(message.error.message));
        else pending.resolve(message.result || {});
      } else {
        for (const handler of this.listeners.get(message.method) || []) handler(message.params || {});
      }
    });
    this.socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) pending.reject(new Error('DevTools connection closed'));
      this.pending.clear();
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolvePromise, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`DevTools command timed out: ${method}`));
      }, TIMEOUT_MS);
      this.pending.set(id, {
        resolve: (value) => { clearTimeout(timer); resolvePromise(value); },
        reject: (error) => { clearTimeout(timer); reject(error); },
      });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  on(method, handler) {
    if (!this.listeners.has(method)) this.listeners.set(method, new Set());
    this.listeners.get(method).add(handler);
    return () => this.listeners.get(method)?.delete(handler);
  }

  close() { this.socket?.close(); }
}

async function connectInitialPage(port) {
  const deadline = Date.now() + TIMEOUT_MS;
  while (Date.now() < deadline) {
    const targets = await jsonEndpoint(port, '/json/list').catch(() => []);
    const target = targets.find((item) => item.type === 'page');
    if (target?.webSocketDebuggerUrl) {
      const client = new CdpClient(target.webSocketDebuggerUrl);
      await client.connect();
      await Promise.all([client.send('Page.enable'), client.send('Runtime.enable'), client.send('Network.enable')]);
      await client.send('Network.setCacheDisabled', { cacheDisabled: true });
      return { client, targetId: target.id };
    }
    await delay(50);
  }
  throw new Error('No debuggable page target appeared');
}

function delay(ms) { return new Promise((accept) => setTimeout(accept, ms)); }

async function evaluate(client, expression) {
  const response = await client.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true, userGesture: true });
  if (response.exceptionDetails) throw new Error(response.exceptionDetails.exception?.description || response.exceptionDetails.text || 'Evaluation failed');
  return response.result?.value;
}

async function until(action, predicate, timeout = 5_000) {
  const deadline = Date.now() + timeout;
  let value;
  while (Date.now() < deadline) {
    value = await action();
    if (predicate(value)) return value;
    await delay(50);
  }
  return value;
}

async function navigate(client, url) {
  // A preceding new-tab check can leave this target backgrounded, which
  // throttles requestAnimationFrame and would turn later motion checks flaky.
  await client.send('Page.bringToFront');
  await client.send('Page.navigate', { url });
  await until(() => evaluate(client, 'document.readyState'), (value) => value === 'complete', TIMEOUT_MS);
  await delay(100);
}

async function discoverPublicRoutes(root) {
  const routes = new Set();
  for (const directory of ['', 'docs']) {
    const full = join(root, directory);
    for (const entry of await readdir(full, { withFileTypes: true }).catch(() => [])) {
      if (entry.isFile() && entry.name.endsWith('.html')) routes.add(`/${directory ? `${directory}/` : ''}${entry.name}`);
    }
  }
  return [...routes].sort().map((route) => route === '/docs/article.html' ? `${route}?post=31-days-ai-day-31.md` : route);
}

function result(id, failures, successes = []) {
  return {
    id,
    status: failures.length ? 'FAIL' : 'PASS',
    detail: failures.length ? failures.join(' | ') : successes.join('; ') || 'All assertions passed.',
  };
}

async function checkNavVisibility(client, baseUrl, routes) {
  const failures = [];
  const viewports = [
    { label: 'desktop', width: 1280, height: 900, mobile: false },
    { label: 'mobile', width: 390, height: 844, mobile: true },
  ];
  for (const viewport of viewports) {
    await client.send('Emulation.setDeviceMetricsOverride', { width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: viewport.mobile });
    for (const route of routes) {
      await navigate(client, `${baseUrl}${route}`);
      const state = await evaluate(client, `(async () => {
        const nav = document.querySelector('#nav, .nav');
        if (!nav) return { exists: false, status: document.body.innerText.slice(0, 80) };
        window.scrollTo(0, 0);
        await new Promise(resolve => setTimeout(resolve, 50));
        const topNav = nav.getBoundingClientRect();
        const contentDeadline = Date.now() + 2000;
        let content = document.querySelector('main h1, main .hero__content, .page-header, .blog-page h1, .days-page h1, #article-content');
        while (!content && Date.now() < contentDeadline) {
          await new Promise(resolve => setTimeout(resolve, 25));
          content = document.querySelector('main h1, main .hero__content, .page-header, .blog-page h1, .days-page h1, #article-content');
        }
        const contentTop = content?.getBoundingClientRect().top ?? null;
        window.scrollTo(0, document.documentElement.scrollHeight);
        await new Promise(resolve => setTimeout(resolve, 350));
        const rect = nav.getBoundingClientRect();
        const style = getComputedStyle(nav);
        return { exists: true, top: rect.top, bottom: rect.bottom, height: rect.height,
          viewport: innerHeight, display: style.display, visibility: style.visibility,
          opacity: Number(style.opacity), scrollY, contentTop, navBottomAtTop: topNav.bottom };
      })()`);
      const visible = state.exists && state.height > 0 && state.top >= -1 && state.bottom <= state.viewport + 1 && state.display !== 'none' && state.visibility !== 'hidden' && state.opacity > 0;
      if (!visible) failures.push(`${viewport.label} ${route}: nav not viewport-visible after downward scroll (${JSON.stringify(state)})`);
      if (state.contentTop === null) failures.push(`${viewport.label} ${route}: primary heading/content did not render`);
      else if (state.contentTop < state.navBottomAtTop - 1) failures.push(`${viewport.label} ${route}: fixed nav overlaps primary content (${JSON.stringify(state)})`);
    }
  }
  await client.send('Emulation.clearDeviceMetricsOverride');
  return result('BEH-1', failures, [`nav stayed visible without covering content on ${routes.length} public pages at desktop and mobile widths`]);
}

async function checkInternalNavigation(client, baseUrl) {
  const failures = [];
  const cases = [['Blog', '/docs/blog.html'], ['Projects', '/projects.html'], ['Reach Out', '/reach-out.html']];
  for (const [label, expected] of cases) {
    await navigate(client, `${baseUrl}${expected}?current-state-test=1`);
    const current = await evaluate(client, `(() => {
      const marked = [...document.querySelectorAll('.nav__link.active, .nav__link[aria-current="page"]')];
      return marked.map(link => ({ text: link.textContent.replace(/\s+/g, ' ').trim(), href: new URL(link.href).pathname, current: link.getAttribute('aria-current') }));
    })()`);
    if (current.length !== 1 || current[0].href !== expected || current[0].current !== 'page') failures.push(`${label}: pathname current state is incorrect ${JSON.stringify(current)}`);
    await navigate(client, `${baseUrl}/index.html?nav-test=${encodeURIComponent(label)}`);
    const found = await evaluate(client, `(() => {
      const link = [...document.querySelectorAll('.nav__link')].find(a => a.textContent.replace(/\\s+/g, ' ').includes(${JSON.stringify(label)}));
      if (!link) return false;
      link.click(); return true;
    })()`);
    if (!found) { failures.push(`${label}: nav link missing`); continue; }
    const actual = await until(() => evaluate(client, 'location.pathname'), (value) => value === expected);
    if (actual !== expected) failures.push(`${label}: expected document navigation to ${expected}, got ${actual}`);
  }
  return result('BEH-2', failures, ['Blog, Projects, and Reach Out performed document navigation with one pathname-based current state']);
}

async function checkTelemetry(client, browserPort, originalTargetId, baseUrl) {
  const failures = [];
  await navigate(client, `${baseUrl}/index.html?telemetry-test=1`);
  const before = await jsonEndpoint(browserPort, '/json/list');
  const metadata = await evaluate(client, `(() => {
    const link = [...document.querySelectorAll('.nav__link')].find(a => a.textContent.includes('Agent Telemetry'));
    if (!link) return null;
    const value = { href: link.href, target: link.target, rel: link.rel };
    link.click(); return value;
  })()`);
  if (!metadata) return result('BEH-3', ['Agent Telemetry nav link missing']);
  if (metadata.target !== '_blank') failures.push(`target expected _blank, got ${metadata.target || '(empty)'}`);
  if (!metadata.rel.split(/\s+/).includes('noopener') || !metadata.rel.split(/\s+/).includes('noreferrer')) failures.push(`rel missing noopener/noreferrer: ${metadata.rel}`);
  const oldIds = new Set(before.map((target) => target.id));
  const after = await until(() => jsonEndpoint(browserPort, '/json/list'), (targets) => targets.some((target) => target.type === 'page' && !oldIds.has(target.id)));
  const opened = after.find((target) => target.type === 'page' && !oldIds.has(target.id));
  if (!opened) failures.push('click did not create a new page target');
  const original = after.find((target) => target.id === originalTargetId);
  if (!original || !original.url.startsWith(baseUrl)) failures.push('original site target was not retained');
  return result('BEH-3', failures, ['Telemetry opened a new target and retained the original page']);
}

async function checkReachOut(client, baseUrl) {
  await navigate(client, `${baseUrl}/reach-out.html?dom-test=1`);
  const state = await evaluate(client, `(() => {
    const text = document.body.innerText.replace(/\\s+/g, ' ');
    const role = [...document.querySelectorAll('a')].find(a => a.textContent.includes('Senior Security Engineer at Coalfire'));
    return {
      title: document.querySelector('h1')?.textContent.trim() || '', text,
      role: role && { href: role.href, target: role.target, rel: role.rel, ariaLabel: role.getAttribute('aria-label') || '', marker: getComputedStyle(role, '::after').content },
      mail: !!document.querySelector('a[href="mailto:${EMAIL}"]'),
      github: !!document.querySelector('a[href*="github.com/josiahH-cf"]'),
      linkedin: !!document.querySelector('a[href*="linkedin.com/in/josiahhunter"]'),
      form: !!document.querySelector('#contactForm'),
    };
  })()`);
  const failures = [];
  const sentence = "I'm a senior security engineer at Coalfire shifting into full time AI engineering, and I've spent years building secure cloud and AI systems on AWS, GCP, and Azure. I love talking about AI, security, cloud, or just human stuff, so let's grab a coffee and chat.";
  if (state.title !== 'Reach Out') failures.push(`expected h1 Reach Out, got ${state.title || '(missing)'}`);
  if (!state.text.includes(sentence)) failures.push('required two-sentence introduction is not rendered verbatim');
  if (!state.role || !/^https:\/\/(?:www\.)?coalfire\.com\/?/.test(state.role.href) || state.role.target !== '_blank') failures.push('Coalfire role link is missing or not a new-tab link');
  else if (!state.role.ariaLabel.includes('opens in a new tab') || !state.role.marker.includes('↗')) failures.push(`Coalfire role link lacks visible/accessibly named external state: ${JSON.stringify(state.role)}`);
  for (const key of ['mail', 'github', 'linkedin', 'form']) if (!state[key]) failures.push(`${key} detail is missing`);
  return result('BEH-5', failures, ['Reach Out content, details, role link, and form rendered']);
}

async function checkContactForm(client, baseUrl) {
  const failures = [];
  await navigate(client, `${baseUrl}/reach-out.html?form-test=email-draft`);
  const initial = await evaluate(client, `(() => {
    const form = document.querySelector('#contactForm');
    const submit = document.querySelector('#contactSubmit');
    const copy = document.querySelector('#copyEmailButton');
    const live = document.querySelector('#contactFormStatus');
    const direct = document.querySelector('#contactEmailLink');
    const controls = form ? Object.fromEntries(['name', 'email', 'message'].map(name => [name, {
      required: form.elements[name]?.required || false,
      maxLength: form.elements[name]?.maxLength || 0,
    }])) : {};
    window.__draftClicks = [];
    window.__fetchCalls = [];
    window.fetch = (...args) => { window.__fetchCalls.push(args.map(String)); return Promise.reject(new Error('network must not be used')); };
    document.addEventListener('click', event => {
      const anchor = event.target.closest?.('a#contactDraftLink');
      if (anchor) {
        window.__draftClicks.push(anchor.getAttribute('href'));
        event.preventDefault();
      }
    }, true);
    let directPreventedBeforeHarness = null;
    direct?.addEventListener('click', event => {
      directPreventedBeforeHarness = event.defaultPrevented;
      event.preventDefault();
      window.__directPreventedBeforeHarness = directPreventedBeforeHarness;
    }, { once: true });
    direct?.click();
    return {
      form: !!form, submitEnabled: !!submit && !submit.disabled,
      submitText: submit?.textContent.trim() || '', copyEnabled: !!copy && !copy.disabled,
      helper: document.querySelector('#contactFormHelp')?.textContent.replace(/\\s+/g, ' ').trim() || '',
      statusRole: live?.getAttribute('role') || '', live: live?.getAttribute('aria-live') || '',
      atomic: live?.getAttribute('aria-atomic') || '',
      directHref: direct?.getAttribute('href') || '', directText: direct?.textContent.trim() || '',
      directPreventedBeforeHarness: window.__directPreventedBeforeHarness,
      controls,
    };
  })()`);
  if (!initial.form) return result('BEH-6', ['contact form missing; email-draft handoff cannot be tested']);
  if (!initial.submitEnabled || initial.submitText !== 'Open Email Draft' || !initial.copyEnabled) failures.push(`progressive-enhancement controls are not enabled correctly: ${JSON.stringify(initial)}`);
  if (!/nothing is sent until you press Send/i.test(initial.helper)) failures.push(`truthful email-draft helper is missing: ${initial.helper}`);
  if (initial.statusRole !== 'status' || initial.live !== 'polite' || initial.atomic !== 'true') failures.push(`live-region semantics are incomplete: ${JSON.stringify(initial)}`);
  if (initial.directHref !== `mailto:${EMAIL}` || initial.directText !== EMAIL || initial.directPreventedBeforeHarness !== false) failures.push(`direct email fallback is not a normal mailto link: ${JSON.stringify(initial)}`);
  const expectedLengths = { name: 100, email: 254, message: 1500 };
  for (const [name, length] of Object.entries(expectedLengths)) {
    if (!initial.controls[name]?.required || initial.controls[name]?.maxLength !== length) failures.push(`${name} field contract is invalid: ${JSON.stringify(initial.controls[name])}`);
  }

  await evaluate(client, `(() => {
    const form = document.querySelector('#contactForm');
    form.elements.name.value = '';
    form.elements.email.value = 'invalid';
    form.elements.message.value = '';
    form.requestSubmit();
  })()`);
  await delay(100);
  let state = await evaluate(client, `(() => ({
    draftClicks: [...window.__draftClicks], fetchCount: window.__fetchCalls.length,
    retryHidden: document.querySelector('#contactDraftLink')?.hidden,
  }))()`);
  if (state.draftClicks.length || state.fetchCount || !state.retryHidden) failures.push(`invalid form opened a draft, used network, or exposed retry: ${JSON.stringify(state)}`);

  await evaluate(client, `(() => {
    const form = document.querySelector('#contactForm');
    form.elements.name.value = 'Browser Tester Bcc: injected@example.com';
    form.elements.email.value = 'browser+site@example.com';
    form.elements.message.value = 'Line one & line two?\\nSecond line.';
    form.requestSubmit();
  })()`);
  await delay(100);
  state = await evaluate(client, `(() => {
    const form = document.querySelector('#contactForm');
    const retry = document.querySelector('#contactDraftLink');
    const live = document.querySelector('#contactFormStatus');
    return {
      draftClicks: [...window.__draftClicks], fetchCount: window.__fetchCalls.length,
      href: retry?.getAttribute('href') || '', retryHidden: retry?.hidden,
      status: document.querySelector('#contactStatusMessage')?.textContent.replace(/\\s+/g, ' ').trim() || '',
      statusState: live?.dataset.state || '',
      name: form.elements.name.value, email: form.elements.email.value, message: form.elements.message.value,
    };
  })()`);
  let draft;
  try { draft = new URL(state.href); } catch { draft = null; }
  if (!draft || draft.protocol !== 'mailto:' || draft.pathname !== EMAIL) failures.push(`draft destination is invalid: ${state.href || '(missing)'}`);
  const subject = draft?.searchParams.get('subject') || '';
  const body = draft?.searchParams.get('body') || '';
  const expectedBody = `Name: ${state.name}\nEmail: ${state.email}\n\n${state.message}`;
  if (subject !== `Website message from ${state.name}` || /[\r\n]/.test(subject)) failures.push(`draft subject is not a sanitized single line: ${JSON.stringify(subject)}`);
  if (body !== expectedBody) failures.push(`draft body is incomplete or incorrectly encoded: ${JSON.stringify({ body, expectedBody })}`);
  if (state.draftClicks.length !== 1 || state.draftClicks[0] !== state.href || state.retryHidden) failures.push(`draft open/retry state is incorrect: ${JSON.stringify(state)}`);
  if (!/review it and press Send there/i.test(state.status) || !/if nothing opened/i.test(state.status) || state.statusState !== 'draft') failures.push(`draft status overclaims delivery or lacks retry guidance: ${JSON.stringify(state)}`);
  if (!state.name || !state.email || !state.message) failures.push('draft handoff cleared form fields');
  if (state.fetchCount) failures.push(`draft handoff unexpectedly used fetch ${state.fetchCount} time(s)`);

  await evaluate(client, `document.querySelector('#contactDraftLink').click()`);
  await delay(50);
  const retryCount = await evaluate(client, `window.__draftClicks.length`);
  if (retryCount !== 2) failures.push(`visible retry link did not reopen the same draft (${retryCount} clicks)`);

  await evaluate(client, `(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      writeText(value) { window.__copiedEmail = String(value); return Promise.resolve(); }
    }});
    document.querySelector('#copyEmailButton').click();
  })()`);
  await delay(100);
  const copySuccess = await evaluate(client, `(() => ({
    copied: window.__copiedEmail || '',
    status: document.querySelector('#contactStatusMessage')?.textContent.trim() || '',
    state: document.querySelector('#contactFormStatus')?.dataset.state || '',
  }))()`);
  if (copySuccess.copied !== EMAIL || copySuccess.status !== 'Email address copied.' || copySuccess.state !== 'copy-success') failures.push(`copy success state is inaccurate: ${JSON.stringify(copySuccess)}`);

  await evaluate(client, `(() => {
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      writeText() { return Promise.reject(new Error('denied')); }
    }});
    document.querySelector('#copyEmailButton').click();
  })()`);
  await delay(100);
  const copyFailure = await evaluate(client, `(() => ({
    status: document.querySelector('#contactStatusMessage')?.textContent.replace(/\\s+/g, ' ').trim() || '',
    state: document.querySelector('#contactFormStatus')?.dataset.state || '',
  }))()`);
  if (!copyFailure.status.startsWith('Copying did not work.') || !copyFailure.status.includes(EMAIL) || copyFailure.state !== 'error') failures.push(`copy failure state is inaccurate: ${JSON.stringify(copyFailure)}`);

  return result('BEH-6', failures, ['validation, encoded draft, retained fields, retry, no-network behavior, and copy success/failure passed']);
}

async function check31Days(client, baseUrl) {
  const failures = [];
  await navigate(client, `${baseUrl}/docs/31-days-of-ai.html?fixed-clock-test=1`);
  const state = await evaluate(client, `(() => {
    const cards = [...document.querySelectorAll('.day-card[data-day]')];
    const originalNow = Date.now;
    let before, dayTen, future;
    try {
      Date.now = () => Date.UTC(2025, 10, 1, 0, 0, 0);
      before = typeof get31DaysAutoDay === 'function' ? get31DaysAutoDay() : null;
      Date.now = () => Date.UTC(2025, 11, 10, 12, 0, 0);
      dayTen = typeof get31DaysAutoDay === 'function' ? get31DaysAutoDay() : null;
      Date.now = () => Date.UTC(2027, 0, 1, 0, 0, 0);
      future = typeof get31DaysAutoDay === 'function' ? get31DaysAutoDay() : null;
    } finally { Date.now = originalNow; }
    return {
      count: cards.length,
      locked: cards.filter(card => card.classList.contains('day-card--locked')).map(card => card.dataset.day),
      nonLive: cards.filter(card => !card.querySelector('.day-card__badge--live')).map(card => card.dataset.day),
      days: cards.map(card => Number(card.dataset.day)),
      headingTags: cards.map(card => card.querySelector('.day-card__title')?.tagName || ''),
      before, dayTen, future,
    };
  })()`);
  if (state.count !== 31 || state.days.some((day, index) => day !== index + 1)) failures.push(`expected ordered cards 1-31, got ${JSON.stringify(state.days)}`);
  if (state.locked.length || state.nonLive.length) failures.push(`completed campaign is not fully live/unlocked: locked=${state.locked}, nonLive=${state.nonLive}`);
  if (state.headingTags.some(tag => tag !== 'H2')) failures.push(`day-card heading hierarchy is invalid: ${JSON.stringify(state.headingTags)}`);
  if (!state.before || state.before.autoDay !== 1) failures.push(`pre-campaign clamp should be day 1: ${JSON.stringify(state.before)}`);
  if (!state.dayTen || state.dayTen.rawDay !== 10 || state.dayTen.autoDay !== 10) failures.push(`fixed day-ten calculation failed: ${JSON.stringify(state.dayTen)}`);
  if (!state.future || state.future.autoDay !== 31) failures.push(`post-campaign clamp should be day 31: ${JSON.stringify(state.future)}`);
  return result('PRES-3', failures, ['31 completed cards and deterministic day 1/10/31 clamping passed']);
}

async function checkHamburger(client, baseUrl, routes) {
  const failures = [];
  await client.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  for (const route of routes) {
    await navigate(client, `${baseUrl}${route}`);
    const state = await evaluate(client, `(async () => {
      const toggle = document.querySelector('#navToggle'); const menu = document.querySelector('#navMenu');
      if (!toggle || !menu) return { exists: false };
      const links = [...menu.querySelectorAll('.nav__link[href]')];
      let closedFocusable = false;
      for (const candidate of links) { candidate.focus(); if (document.activeElement === candidate) closedFocusable = true; }
      const closed = { visibility: getComputedStyle(menu).visibility, expanded: toggle.getAttribute('aria-expanded'), focusable: closedFocusable };
      toggle.click(); await new Promise(r => setTimeout(r, 20));
      const opened = { menu: menu.classList.contains('active'), toggle: toggle.classList.contains('active'), visibility: getComputedStyle(menu).visibility, expanded: toggle.getAttribute('aria-expanded'), focusEntered: menu.contains(document.activeElement) };
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await new Promise(r => setTimeout(r, 20));
      const escaped = { menu: menu.classList.contains('active'), toggle: toggle.classList.contains('active'), expanded: toggle.getAttribute('aria-expanded'), focusReturned: document.activeElement === toggle };
      toggle.click(); await new Promise(r => setTimeout(r, 20));
      const link = links[0];
      link?.addEventListener('click', e => e.preventDefault(), { once: true }); link?.click(); await new Promise(r => setTimeout(r, 20));
      const linked = { menu: menu.classList.contains('active'), toggle: toggle.classList.contains('active'), expanded: toggle.getAttribute('aria-expanded') };
      return { exists: true, closed, opened, escaped, linked };
    })()`);
    if (!state.exists) { failures.push(`${route}: toggle/menu missing`); continue; }
    if (state.closed.visibility !== 'hidden' || state.closed.expanded !== 'false' || state.closed.focusable) failures.push(`${route}: closed menu remains exposed to keyboard focus ${JSON.stringify(state.closed)}`);
    if (!state.opened.menu || !state.opened.toggle || state.opened.visibility !== 'visible' || state.opened.expanded !== 'true' || !state.opened.focusEntered) failures.push(`${route}: class/ARIA/focus open state incorrect ${JSON.stringify(state.opened)}`);
    if (state.escaped.menu || state.escaped.toggle || state.escaped.expanded !== 'false' || !state.escaped.focusReturned) failures.push(`${route}: Escape did not close and return focus ${JSON.stringify(state.escaped)}`);
    if (state.linked.menu || state.linked.toggle || state.linked.expanded !== 'false') failures.push(`${route}: link did not close the menu ${JSON.stringify(state.linked)}`);
  }
  await client.send('Emulation.setDeviceMetricsOverride', { width: 375, height: 240, deviceScaleFactor: 1, mobile: true });
  await navigate(client, `${baseUrl}/index.html?compact-menu-test=1`);
  const compact = await evaluate(client, `(async () => {
    const toggle = document.querySelector('#navToggle'); const menu = document.querySelector('#navMenu');
    toggle?.click(); await new Promise(r => setTimeout(r, 20));
    const last = [...(menu?.querySelectorAll('.nav__link[href]') || [])].at(-1);
    last?.scrollIntoView({ block: 'nearest' }); await new Promise(r => setTimeout(r, 20));
    const menuRect = menu?.getBoundingClientRect(); const linkRect = last?.getBoundingClientRect();
    return { overflowY: menu && getComputedStyle(menu).overflowY, scrollTop: menu?.scrollTop || 0,
      clientHeight: menu?.clientHeight || 0, scrollHeight: menu?.scrollHeight || 0,
      reachable: !!menuRect && !!linkRect && linkRect.top >= menuRect.top - 1 && linkRect.bottom <= menuRect.bottom + 1 };
  })()`);
  if (!['auto', 'scroll'].includes(compact.overflowY) || compact.scrollHeight > compact.clientHeight && (!compact.reachable || compact.scrollTop <= 0)) failures.push(`compact-height menu cannot reach its final item ${JSON.stringify(compact)}`);
  await client.send('Emulation.clearDeviceMetricsOverride');
  return result('PRES-4', failures, [`mobile hidden-focus, open-focus, Escape, link-close, and compact scrolling passed on ${routes.length} existing pages`]);
}

async function checkReveal(client, baseUrl) {
  const failures = [];
  await client.send('Emulation.setEmulatedMedia', { media: 'screen', features: [{ name: 'prefers-reduced-motion', value: 'no-preference' }] });
  await navigate(client, `${baseUrl}/index.html?reveal-test=normal`);
  let normal = await evaluate(client, `(async () => {
    const element = document.querySelector('.reveal-on-scroll'); if (!element) return { exists: false };
    element.scrollIntoView({ block: 'center', behavior: 'instant' });
    const deadline = performance.now() + 1500;
    while (!element.classList.contains('revealed') && performance.now() < deadline) {
      await new Promise(r => setTimeout(r, 25));
    }
    return { exists: true, revealed: element.classList.contains('revealed') };
  })()`);
  if (!normal.exists || !normal.revealed) failures.push(`normal reveal behavior failed: ${JSON.stringify(normal)}`);
  await client.send('Emulation.setEmulatedMedia', { media: 'screen', features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  await navigate(client, `${baseUrl}/index.html?reveal-test=reduce`);
  const reduced = await evaluate(client, `(() => {
    const elements = [...document.querySelectorAll('.fade-in, .reveal-on-scroll')];
    const zeroMotion = element => {
      const style = getComputedStyle(element);
      const times = (value) => value.split(',').map(part => parseFloat(part) || 0);
      return times(style.animationDuration).every(value => value === 0) && times(style.transitionDuration).every(value => value === 0);
    };
    return { matches: matchMedia('(prefers-reduced-motion: reduce)').matches, count: elements.length,
      allRevealed: elements.every(e => e.classList.contains('revealed')),
      allDisabled: elements.every(zeroMotion) };
  })()`);
  if (!reduced.matches || !reduced.count || !reduced.allRevealed || !reduced.allDisabled) failures.push(`reduced-motion behavior failed: ${JSON.stringify(reduced)}`);
  await client.send('Emulation.setEmulatedMedia', { media: 'screen', features: [] });
  return result('PRES-5', failures, ['normal reveal and reduced-motion immediate reveal passed']);
}

async function checkSocialAndClipboard(client, baseUrl) {
  const failures = [];
  await client.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  await navigate(client, `${baseUrl}/index.html?social-test=desktop`);
  const desktop = await evaluate(client, `(async () => {
    const sidebar = document.querySelector('.social-sidebar'); const email = document.querySelector('#emailLink');
    const external = [...(sidebar?.querySelectorAll('a[href^="http"]') || [])];
    email?.addEventListener('click', event => {
      window.__emailPreventedBeforeHarness = event.defaultPrevented;
      event.preventDefault();
    }, { once: true });
    email?.click(); await new Promise(r => setTimeout(r, 50));
    return { sidebar: !!sidebar, visible: sidebar && getComputedStyle(sidebar).display !== 'none', email: email?.getAttribute('href'),
      preventedBeforeHarness: window.__emailPreventedBeforeHarness,
      tooltip: document.body.innerText.includes('Email copied!'),
      safeExternal: external.length >= 2 && external.every(a => a.target === '_blank' && a.rel.split(/\\s+/).includes('noopener') && a.rel.split(/\\s+/).includes('noreferrer')) };
  })()`);
  if (!desktop.sidebar || !desktop.visible) failures.push('desktop social sidebar missing or hidden');
  if (desktop.email !== `mailto:${EMAIL}` || desktop.preventedBeforeHarness !== false || desktop.tooltip) failures.push(`desktop email link is not a normal, unambiguous mailto action: ${JSON.stringify(desktop)}`);
  if (!desktop.safeExternal) failures.push('social external links lack safe new-tab attributes');
  await client.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await navigate(client, `${baseUrl}/index.html?social-test=mobile`);
  const mobileHidden = await evaluate(client, `(() => { const sidebar = document.querySelector('.social-sidebar'); return !!sidebar && getComputedStyle(sidebar).display === 'none'; })()`);
  if (!mobileHidden) failures.push('social sidebar is not hidden at mobile width');
  await client.send('Emulation.clearDeviceMetricsOverride');
  return result('PRES-6', failures, ['desktop social links keep normal destinations and the rail hides on mobile']);
}

async function checkHeroFit(client, baseUrl) {
  const failures = [];
  const rectsOverlap = (a, b) => !!a && !!b
    && Math.min(a.right, b.right) > Math.max(a.left, b.left) + 1
    && Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top) + 1;
  const viewports = [
    { label: 'desktop', width: 1440, height: 900, desktop: true },
    { label: 'tall desktop', width: 1200, height: 1600, desktop: true },
    { label: 'laptop', width: 1366, height: 768, desktop: true },
    { label: 'scaled desktop', width: 1173, height: 579, desktop: true },
    { label: 'compact desktop', width: 1024, height: 600, desktop: true },
    { label: 'desktop breakpoint', width: 901, height: 768, desktop: true },
    { label: 'narrow tablet', width: 820, height: 700, desktop: false },
    { label: 'tablet', width: 768, height: 1024, desktop: false },
    { label: 'mobile', width: 390, height: 844, desktop: false },
    { label: 'narrow mobile', width: 375, height: 667, desktop: false },
    { label: 'small mobile', width: 320, height: 568, desktop: false },
  ];
  for (const viewport of viewports) {
    await client.send('Emulation.setDeviceMetricsOverride', {
      width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: !viewport.desktop,
    });
    await navigate(client, `${baseUrl}/index.html?hero-fit=${encodeURIComponent(viewport.label)}`);
    await delay(900);
    const state = await evaluate(client, `(() => {
      const rect = element => {
        const value = element?.getBoundingClientRect();
        return value && { left: value.left, right: value.right, top: value.top, bottom: value.bottom, width: value.width, height: value.height };
      };
      const lineCount = element => {
        if (!element) return 0;
        const range = document.createRange(); range.selectNodeContents(element);
        const tops = [];
        for (const value of range.getClientRects()) {
          if (!value.width || !value.height) continue;
          if (!tops.some(top => Math.abs(top - value.top) < 1)) tops.push(value.top);
        }
        return tops.length;
      };
      const overlap = (a, b) => !!a && !!b && Math.min(a.right, b.right) > Math.max(a.left, b.left) + 1 && Math.min(a.bottom, b.bottom) > Math.max(a.top, b.top) + 1;
      const hero = document.querySelector('.hero');
      const nav = document.querySelector('.nav');
      const container = document.querySelector('.hero__container');
      const content = document.querySelector('.hero__content');
      const visual = document.querySelector('.hero__visual');
      const split = document.querySelector('.split-card');
      const greeting = document.querySelector('.hero__greeting');
      const name = document.querySelector('.hero__name');
      const prompt = document.querySelector('.hero__conversation-prompt');
      const topics = document.querySelector('ul.hero__topics');
      const topicItems = [...(topics?.querySelectorAll('li.hero__topic') || [])];
      const ctaGroup = document.querySelector('.hero__cta-group');
      const socialGroup = document.querySelector('.hero__social');
      const sidebar = document.querySelector('.social-sidebar');
      const homeBlog = document.querySelector('section.articles--home');
      const homeBlogList = homeBlog?.querySelector('.articles__list');
      const homeBlogCards = [...(homeBlogList?.querySelectorAll('.article-card') || [])];
      const visibleHomeBlogCards = homeBlogCards.filter(item => getComputedStyle(item).display !== 'none');
      const homeBlogIntro = homeBlog?.querySelector('.home-blog__intro');
      const homeBlogAll = homeBlog?.querySelector('a.home-blog__all-link');
      const homeSeries = homeBlog?.querySelector('a.home-series-link');
      const ctas = [...document.querySelectorAll('.hero__cta')];
      const socials = [...document.querySelectorAll('.hero__social-link')];
      const interactive = [...document.querySelectorAll('.hero a, .hero button')];
      const socialData = socials.map(link => ({
        href: link.href, target: link.target, rel: link.rel, ariaLabel: link.getAttribute('aria-label') || '',
        link: rect(link), icon: rect(link.querySelector('svg')),
      }));
      const ordered = [greeting, name, prompt, topics, ctaGroup, socialGroup];
      const xClipped = [...document.querySelectorAll('.hero__content, .hero__visual, .split-card, .hero__topic, .hero a')]
        .map(element => ({ selector: element.className, rect: rect(element) }))
        .filter(item => item.rect && (item.rect.left < -1 || item.rect.right > innerWidth + 1));
      return {
        viewport: { width: innerWidth, height: innerHeight },
        horizontalOverflow: document.documentElement.scrollWidth - innerWidth,
        hero: rect(hero), nav: rect(nav), container: rect(container), content: rect(content), visual: rect(visual), split: rect(split),
        greeting: rect(greeting), name: rect(name), prompt: rect(prompt), topicsRect: rect(topics),
        ctaGroup: rect(ctaGroup), socialGroup: rect(socialGroup),
        sidebarVisible: !!sidebar && getComputedStyle(sidebar).display !== 'none' && getComputedStyle(sidebar).visibility !== 'hidden',
        nameText: name?.textContent.trim() || '', promptText: prompt?.textContent.trim() || '',
        nameLines: lineCount(name), promptLines: lineCount(prompt),
        nameFont: name ? parseFloat(getComputedStyle(name).fontSize) : 0,
        topicListTag: topics?.tagName || '',
        topicsLabel: topics?.getAttribute('aria-label') || '',
        topics: topicItems.map(item => {
          const label = item.querySelector('.hero__topic-label');
          const style = getComputedStyle(item);
          return {
            tag: item.tagName, rect: rect(item),
            emoji: item.querySelector('.hero__topic-emoji')?.textContent.trim() || '',
            emojiHidden: item.querySelector('.hero__topic-emoji')?.getAttribute('aria-hidden') || '',
            label: label?.textContent.trim() || '',
            contentOverflow: Math.max(0, item.scrollWidth - item.clientWidth),
            labelOverflow: label ? Math.max(0, label.scrollWidth - label.clientWidth) : 0,
            background: style.backgroundColor,
            borderWidths: [style.borderTopWidth, style.borderRightWidth, style.borderBottomWidth, style.borderLeftWidth],
            cursor: style.cursor, transform: style.transform,
            role: item.getAttribute('role') || '', tabindex: item.getAttribute('tabindex'),
            interactiveDescendants: item.querySelectorAll('a, button, input, select, textarea').length,
          };
        }),
        homeBlog: {
          exists: !!homeBlog,
          intro: homeBlogIntro?.textContent.replace(/\\s+/g, ' ').trim() || '',
          introReveals: homeBlogIntro?.classList.contains('reveal-on-scroll') || false,
          allHref: homeBlogAll?.getAttribute('href') || '', allText: homeBlogAll?.textContent.trim() || '',
          seriesHref: homeSeries?.getAttribute('href') || '', seriesText: homeSeries?.textContent.replace(/\\s+/g, ' ').trim() || '',
          campaignCount: homeBlog?.querySelectorAll('.campaign-banner').length || 0,
          allCardCount: homeBlogCards.length,
          visibleCardRects: visibleHomeBlogCards.map(rect),
          gridColumns: homeBlogList ? getComputedStyle(homeBlogList).gridTemplateColumns.split(/\\s+/).filter(Boolean).length : 0,
          overflow: homeBlog ? Math.max(0, homeBlog.scrollWidth - homeBlog.clientWidth) : -1,
        },
        domOrdered: ordered.every(Boolean) && ordered.slice(0, -1).every((item, index) => !!(item.compareDocumentPosition(ordered[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING)),
        containerContentLeft: container ? rect(container).left + parseFloat(getComputedStyle(container).paddingLeft) : 0,
        containerContentRight: container ? rect(container).right - parseFloat(getComputedStyle(container).paddingRight) : 0,
        gridColumnCount: container ? getComputedStyle(container).gridTemplateColumns.split(/\\s+/).filter(Boolean).length : 0,
        ctas: ctas.map(item => ({ ...rect(item), lines: lineCount(item), contentOverflow: Math.max(0, item.scrollWidth - item.clientWidth) })), socials: socialData, xClipped,
        contentVisualOverlap: overlap(rect(content), rect(visual)),
        ctaOverlap: ctas.length === 2 && overlap(rect(ctas[0]), rect(ctas[1])),
        socialOverlap: socials.some((link, index) => socials.slice(index + 1).some(other => overlap(rect(link), rect(other)))),
        interactiveClipped: interactive.map(rect).filter(value => value && (value.left < -1 || value.right > innerWidth + 1)),
      };
    })()`);
    const prefix = `${viewport.label} ${viewport.width}x${viewport.height}`;
    const expectedTopics = JSON.stringify([['🔐', 'Security'], ['☁️', 'Cloud'], ['🧠', 'AI']]);
    const actualTopics = JSON.stringify(state.topics.map(item => [item.emoji, item.label]));
    if (state.horizontalOverflow > 1 || state.xClipped.length || state.interactiveClipped.length) failures.push(`${prefix}: horizontal clipping/overflow ${JSON.stringify(state)}`);
    if (state.ctaOverlap || state.socialOverlap) failures.push(`${prefix}: hero actions overlap ${JSON.stringify(state)}`);
    if (state.ctas.some(item => item.lines !== 1 || item.contentOverflow > 1)) failures.push(`${prefix}: CTA text wraps or clips ${JSON.stringify(state.ctas)}`);
    if (state.nameText !== 'Josiah Hunter' || state.promptText !== 'I love to chat about...' || actualTopics !== expectedTopics || state.topicListTag !== 'UL' || state.topicsLabel !== 'Topics I love to chat about' || state.topics.some(item => item.tag !== 'LI' || item.emojiHidden !== 'true')) failures.push(`${prefix}: intro copy/topic semantics are wrong ${JSON.stringify({ name: state.nameText, prompt: state.promptText, topicsLabel: state.topicsLabel, topics: state.topics })}`);
    if (!state.domOrdered || !state.name || !state.prompt || !state.topicsRect || !state.ctaGroup || !state.socialGroup || state.name.bottom > state.prompt.top + 1 || state.prompt.bottom > state.topicsRect.top + 1 || state.topicsRect.bottom > state.ctaGroup.top + 1 || state.ctaGroup.bottom > state.socialGroup.top + 1) failures.push(`${prefix}: intro hierarchy/order is not visually coherent ${JSON.stringify(state)}`);
    if (state.topics.some(item => item.contentOverflow > 1 || item.labelOverflow > 1) || state.topics.some((item, index) => state.topics.slice(index + 1).some(other => rectsOverlap(item.rect, other.rect)))) failures.push(`${prefix}: topic tags overlap or contain clipped text ${JSON.stringify(state.topics)}`);
    if (state.topics.some(item => item.background !== 'rgba(0, 0, 0, 0)' || item.borderWidths.some(width => width !== '0px') || item.cursor === 'pointer' || item.transform !== 'none' || item.role || item.tabindex !== null || item.interactiveDescendants)) failures.push(`${prefix}: interests still look or behave like interactive blocks ${JSON.stringify(state.topics)}`);
    if (state.socials.length !== 3 || state.socials.some(item => item.icon.width < 28 || item.icon.height < 28 || item.link.width < 44 || item.link.height < 44)) failures.push(`${prefix}: social icon/target sizing is too small ${JSON.stringify(state.socials)}`);
    const expectedHrefs = ['https://github.com/josiahH-cf', 'https://www.linkedin.com/in/josiahhunter/', `mailto:${EMAIL}`];
    if (state.socials.some((item, index) => !item.href.startsWith(expectedHrefs[index]))) failures.push(`${prefix}: social destinations changed ${JSON.stringify(state.socials)}`);
    if (state.socials.slice(0, 2).some(item => item.target !== '_blank' || !item.rel.split(/\s+/).includes('noopener') || !item.rel.split(/\s+/).includes('noreferrer'))) failures.push(`${prefix}: external social safety attributes missing`);
    if (state.socials.slice(0, 2).some(item => !item.ariaLabel.toLowerCase().includes('new tab'))) failures.push(`${prefix}: external social accessible name does not announce new-tab behavior`);
    const home = state.homeBlog;
    if (!home.exists || home.intro !== 'Ideas, experiments, and the occasional useful rabbit hole.' || !home.introReveals || home.allHref !== '/docs/blog.html' || home.allText !== 'See all writing →' || home.seriesHref !== '/docs/31-days-of-ai.html' || home.seriesText !== 'A completed side quest: 31 Days of AI — 31 entries →' || home.campaignCount !== 0 || home.allCardCount !== 5 || home.visibleCardRects.length !== 3) failures.push(`${prefix}: lightweight home Blog structure/copy is incomplete ${JSON.stringify(home)}`);
    if (home.overflow > 1) failures.push(`${prefix}: home Blog overflows its section by ${home.overflow}px`);
    if (viewport.width > 900) {
      if (home.gridColumns !== 3 || home.visibleCardRects.some((item, index) => index && Math.abs(item.top - home.visibleCardRects[0].top) > 10) || home.visibleCardRects.some((item, index) => index && Math.abs(item.width - home.visibleCardRects[0].width) > 12)) failures.push(`${prefix}: home Blog is not a clean three-column desktop row ${JSON.stringify(home)}`);
    } else if (viewport.width > 640) {
      if (home.gridColumns !== 2 || home.visibleCardRects[0]?.width < (home.visibleCardRects[1]?.width || Infinity) * 1.7 || Math.abs((home.visibleCardRects[1]?.top || 0) - (home.visibleCardRects[2]?.top || 0)) > 10) failures.push(`${prefix}: home Blog tablet composition is not one lead card over two columns ${JSON.stringify(home)}`);
    } else if (home.gridColumns !== 1 || home.visibleCardRects.some((item, index) => index && (Math.abs(item.left - home.visibleCardRects[0].left) > 4 || Math.abs(item.width - home.visibleCardRects[0].width) > 8))) {
      failures.push(`${prefix}: home Blog is not a readable single-column mobile stack ${JSON.stringify(home)}`);
    }
    if (viewport.desktop) {
      const lowest = Math.max(state.content.bottom, state.visual.bottom, ...state.ctas.map(value => value.bottom), ...state.socials.map(value => value.link.bottom));
      if (state.gridColumnCount !== 2 || !state.container || Math.abs(state.content.left - state.containerContentLeft) > 1 || Math.abs(state.split.right - state.containerContentRight) > 1 || state.visual.left - state.content.right < 24 || state.content.width < state.container.width * 0.3 || state.visual.width < state.container.width * 0.3) failures.push(`${prefix}: desktop hero columns are not clearly aligned ${JSON.stringify({ container: state.container, containerContentLeft: state.containerContentLeft, containerContentRight: state.containerContentRight, content: state.content, visual: state.visual, split: state.split, gridColumnCount: state.gridColumnCount })}`);
      if ([state.greeting, state.name, state.prompt, state.topicsRect, state.ctaGroup, state.socialGroup].some(value => Math.abs(value.left - state.content.left) > 1) || Math.abs((state.content.top + state.content.bottom) / 2 - (state.split.top + state.split.bottom) / 2) > 2) failures.push(`${prefix}: content groups or column centers are visibly ragged ${JSON.stringify({ content: state.content, greeting: state.greeting, name: state.name, prompt: state.prompt, topics: state.topicsRect, ctaGroup: state.ctaGroup, socialGroup: state.socialGroup, split: state.split })}`);
      if (state.nameLines !== 1 || state.promptLines !== 1) failures.push(`${prefix}: desktop name/prompt wraps (${state.nameLines}/${state.promptLines} lines)`);
      if (state.nameFont > 64.1 || state.split.width > 440.1 || state.split.height > 300.1) failures.push(`${prefix}: type or visual exceeds compact bounds ${JSON.stringify({ nameFont: state.nameFont, split: state.split })}`);
      if (state.ctas.length !== 2 || Math.abs(state.ctas[0].top - state.ctas[1].top) > 1 || Math.abs(state.ctas[0].width - state.ctas[1].width) > 2 || Math.abs(state.ctas[0].height - state.ctas[1].height) > 1) failures.push(`${prefix}: CTA columns are not aligned/equal ${JSON.stringify(state.ctas)}`);
      if (state.topics.length !== 3 || state.topics.some(item => Math.abs(item.rect.top - state.topics[0].rect.top) > 1)) failures.push(`${prefix}: desktop interests are not a clean inline row ${JSON.stringify(state.topics)}`);
      if (state.contentVisualOverlap) failures.push(`${prefix}: content and split card overlap`);
      if (viewport.height <= 700 && state.sidebarVisible) failures.push(`${prefix}: fixed social rail remains visible on a short screen`);
      if (Math.min(state.content.top, state.visual.top) < state.nav.bottom - 1 || lowest > state.viewport.height + 1) failures.push(`${prefix}: required hero content does not fit the first screen ${JSON.stringify({ nav: state.nav, content: state.content, visual: state.visual, lowest })}`);
      if (state.hero.height > 900 || Math.min(state.content.top, state.visual.top) - state.nav.bottom > 240) failures.push(`${prefix}: desktop hero has excessive whitespace ${JSON.stringify({ hero: state.hero, nav: state.nav, content: state.content, visual: state.visual })}`);
    } else {
      if (state.gridColumnCount !== 1 || state.visual.top < state.content.bottom + 20) failures.push(`${prefix}: responsive hero is not a clean stacked layout ${JSON.stringify({ content: state.content, visual: state.visual, gridColumnCount: state.gridColumnCount })}`);
      const contentCenter = (state.content.left + state.content.right) / 2;
      if ([state.topicsRect, state.ctaGroup, state.socialGroup, state.split].some(value => Math.abs((value.left + value.right) / 2 - contentCenter) > 2) || state.ctas.length !== 2 || Math.abs(state.ctas[0].width - state.ctas[1].width) > 2) failures.push(`${prefix}: responsive groups are not centered/equal ${JSON.stringify({ content: state.content, topics: state.topicsRect, ctaGroup: state.ctaGroup, ctas: state.ctas, socialGroup: state.socialGroup, split: state.split })}`);
      if (state.hero.bottom + 1 < Math.max(state.content.bottom, state.visual.bottom)) failures.push(`${prefix}: responsive hero clips its stacked content`);
    }
  }
  await client.send('Emulation.clearDeviceMetricsOverride');
  return result('BEH-9', failures, ['natural intro hierarchy, plain interests, light home Blog, aligned columns, and enlarged social icons passed across eleven viewports']);
}

async function checkGitHubActivity(client, baseUrl) {
  const failures = [];
  const viewports = [
    { label: 'desktop', width: 1440, height: 900, mobile: false },
    { label: 'tablet', width: 768, height: 1024, mobile: true },
    { label: 'mobile', width: 390, height: 844, mobile: true },
    { label: 'small mobile', width: 320, height: 568, mobile: true },
  ];
  for (const viewport of viewports) {
    await client.send('Emulation.setDeviceMetricsOverride', {
      width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: viewport.mobile,
    });
    await navigate(client, `${baseUrl}/projects.html?github-activity=${encodeURIComponent(viewport.label)}`);
    await delay(250);
    const state = await evaluate(client, `(async () => {
      const rect = element => {
        const value = element?.getBoundingClientRect();
        return value && { left: value.left, right: value.right, top: value.top, bottom: value.bottom, width: value.width, height: value.height };
      };
      const activity = document.querySelector('.github-activity');
      const pageHeader = document.querySelector('.projects-page .page-header');
      const pageTitle = pageHeader?.querySelector('h1');
      const subtitle = pageHeader?.querySelector('.projects-page__subtitle');
      const heading = activity?.querySelector('h2.github-activity__title');
      const time = activity?.querySelector('time.github-activity__year');
      const status = activity?.querySelector('.github-activity__status');
      const list = activity?.querySelector('dl.github-activity__highlights');
      const metrics = [...(list?.querySelectorAll('.github-activity-highlight') || [])];
      const figure = activity?.querySelector('figure.github-activity__rhythm');
      const caption = figure?.querySelector('figcaption');
      const frame = figure?.querySelector('.github-activity__calendar-frame');
      const calendar = frame?.querySelector('svg.github-activity-calendar');
      const days = [...(calendar?.querySelectorAll('rect.github-activity-day') || [])];
      const legend = figure?.querySelector('.github-activity__legend');
      const legendSwatches = [...(legend?.querySelectorAll('[data-level]') || [])];
      const labelledIds = (calendar?.getAttribute('aria-labelledby') || '').split(/\\s+/).filter(Boolean);
      const cta = document.querySelector('a.github-dashboard-cta');
      const beforeScroll = rect(cta);
      document.documentElement.style.scrollBehavior = 'auto';
      cta?.scrollIntoView({ block: 'center' });
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const ctaRect = rect(cta);
      const clipped = [...metrics, figure, frame, cta].filter(Boolean).map(element => ({
        className: element.className, rect: rect(element),
      })).filter(item => item.rect.left < -1 || item.rect.right > innerWidth + 1);
      const dayData = days.map(day => ({
        date: day.getAttribute('data-date') || '',
        count: day.getAttribute('data-count') || '',
        level: day.getAttribute('data-level') || '',
        title: day.querySelector('title')?.textContent.trim() || '',
        fill: getComputedStyle(day).fill,
      }));
      return {
        subtitle: subtitle?.textContent.trim() || '',
        subtitleDirectlyAfterTitle: !!pageTitle && !!subtitle && pageTitle.nextElementSibling === subtitle,
        sectionCount: document.querySelectorAll('.github-activity').length,
        heading: heading?.textContent.trim() || '', labelledBy: activity?.getAttribute('aria-labelledby') || '', headingId: heading?.id || '',
        timeText: time?.textContent.trim() || '', datetime: time?.getAttribute('datetime') || '', statusText: status?.textContent.trim() || '',
        listCount: activity?.querySelectorAll('dl.github-activity__highlights').length || 0,
        metrics: metrics.map(item => ({
          key: item.getAttribute('data-github-metric') || '',
          value: item.querySelector('dd')?.textContent.trim() || '',
          label: item.querySelector('dt')?.textContent.trim() || '',
          rect: rect(item),
        })),
        figureCount: activity?.querySelectorAll('figure.github-activity__rhythm').length || 0,
        figureLabelledBy: figure?.getAttribute('aria-labelledby') || '', captionId: caption?.id || '',
        caption: caption?.textContent.replace(/\\s+/g, ' ').trim() || '',
        calendarRole: calendar?.getAttribute('role') || '', calendarLabelledIds: labelledIds,
        calendarLabelsResolve: labelledIds.length === 2 && labelledIds.every(id => !!document.getElementById(id)),
        calendarTitle: calendar?.querySelector('title')?.textContent.trim() || '',
        calendarDescription: calendar?.querySelector('desc')?.textContent.trim() || '',
        monthCount: calendar?.querySelectorAll('.github-activity-calendar__month').length || 0,
        weekdays: [...(calendar?.querySelectorAll('.github-activity-calendar__weekday') || [])].map(item => item.textContent.trim()),
        dayData,
        legendLevels: legendSwatches.map(item => item.getAttribute('data-level')),
        legendFills: legendSwatches.map(item => getComputedStyle(item).backgroundColor),
        legendText: legend?.textContent.replace(/\\s+/g, ' ').trim() || '',
        frameRect: rect(frame), calendarRect: rect(calendar),
        frameOverflowX: frame ? getComputedStyle(frame).overflowX : '',
        frameScrollable: !!frame && frame.scrollWidth > frame.clientWidth + 1,
        href: cta?.getAttribute('href') || '', target: cta?.target || '', rel: cta?.rel || '',
        accessible: ((cta?.getAttribute('aria-label') || '') + ' ' + (cta?.textContent || '')).trim(),
        follows: !!activity && !!cta && !!(activity.compareDocumentPosition(cta) & Node.DOCUMENT_POSITION_FOLLOWING),
        activityRect: rect(activity), beforeScroll, ctaRect, clipped,
        overflow: document.documentElement.scrollWidth - innerWidth,
        reachable: !!ctaRect && ctaRect.top >= -1 && ctaRect.bottom <= innerHeight + 1,
      };
    })()`);
    const prefix = `${viewport.label} ${viewport.width}x${viewport.height}`;
    if (state.subtitle !== 'top projects' || !state.subtitleDirectlyAfterTitle) failures.push(`${prefix}: exact Projects subtitle is absent or misplaced`);
    const keys = state.metrics.map(item => item.key);
    const expectedKeys = ['contributions', 'commits', 'pull-requests'];
    if (state.sectionCount !== 1 || !state.heading || state.listCount !== 1 || state.metrics.length !== 3 || state.figureCount !== 1) failures.push(`${prefix}: activity structure is incomplete ${JSON.stringify(state)}`);
    if (state.labelledBy !== state.headingId || !state.headingId) failures.push(`${prefix}: activity section is not labelled by its heading`);
    if (JSON.stringify(keys) !== JSON.stringify(expectedKeys) || new Set(keys).size !== 3) failures.push(`${prefix}: headline metric keys/order are invalid ${JSON.stringify(keys)}`);
    if (state.metrics.some(item => !/^\d{1,3}(,\d{3})*$/.test(item.value) || !item.label)) failures.push(`${prefix}: activity values/labels are invalid ${JSON.stringify(state.metrics)}`);
    const year = state.datetime.match(/^\d{4}$/)?.[0] || '';
    if (!year || state.timeText !== year || !state.heading.startsWith(`${year} `) || !/year-to-date public contribution totals/i.test(state.statusText) || !/refreshed daily/i.test(state.statusText)) failures.push(`${prefix}: year/scope/cadence are inconsistent ${JSON.stringify({ heading: state.heading, datetime: state.datetime, timeText: state.timeText, statusText: state.statusText })}`);
    const expectedDays = year && new Date(Date.UTC(Number(year), 1, 29)).getUTCDate() === 29 ? 366 : 365;
    const dates = state.dayData.map(day => day.date);
    const dayTotal = state.dayData.reduce((sum, day) => sum + (/^\d+$/.test(day.count) ? Number(day.count) : 0), 0);
    const contributionTotal = Number((state.metrics.find(item => item.key === 'contributions')?.value || '').replace(/,/g, ''));
    if (state.figureLabelledBy !== state.captionId || !state.captionId || !/contribution rhythm/i.test(state.caption) || state.calendarRole !== 'img' || !state.calendarLabelsResolve || !state.calendarTitle || !state.calendarDescription) failures.push(`${prefix}: contribution graph accessible naming is incomplete ${JSON.stringify(state)}`);
    if (state.monthCount !== 12 || JSON.stringify(state.weekdays) !== JSON.stringify(['Mon', 'Wed', 'Fri']) || state.dayData.length !== expectedDays) failures.push(`${prefix}: contribution graph axes/day coverage are incomplete ${JSON.stringify({ monthCount: state.monthCount, weekdays: state.weekdays, days: state.dayData.length, expectedDays })}`);
    if (dates.some(date => !new RegExp(`^${year}-\\d{2}-\\d{2}$`).test(date)) || dates.some((date, index) => index && date <= dates[index - 1]) || new Set(dates).size !== dates.length || state.dayData.some(day => !/^\d+$/.test(day.count) || !/^[0-4]$/.test(day.level) || !day.title) || dayTotal !== contributionTotal) failures.push(`${prefix}: contribution cells are invalid or do not reconcile ${JSON.stringify({ dayTotal, contributionTotal, first: state.dayData[0], last: state.dayData.at(-1) })}`);
    if (JSON.stringify(state.legendLevels) !== JSON.stringify(['0', '1', '2', '3', '4']) || !/^Less\s+More$/.test(state.legendText) || new Set(state.legendFills).size !== 5) failures.push(`${prefix}: contribution intensity encoding/legend is incomplete ${JSON.stringify({ legendLevels: state.legendLevels, legendText: state.legendText, fills: state.legendFills })}`);
    if (viewport.width <= 390 && (!state.frameScrollable || !['auto', 'scroll'].includes(state.frameOverflowX))) failures.push(`${prefix}: narrow contribution graph is not locally scrollable ${JSON.stringify({ frameScrollable: state.frameScrollable, overflowX: state.frameOverflowX, frame: state.frameRect, calendar: state.calendarRect })}`);
    if (viewport.width >= 900 && (state.metrics.some((item, index) => index && Math.abs(item.rect.top - state.metrics[0].rect.top) > 1) || state.metrics.some((item, index) => index && Math.abs(item.rect.width - state.metrics[0].rect.width) > 3))) failures.push(`${prefix}: headline metrics are not aligned as three equal columns ${JSON.stringify(state.metrics)}`);
    if (state.href !== 'https://github.com/josiahH-cf' || state.target !== '_blank' || !state.rel.split(/\s+/).includes('noopener') || !state.rel.split(/\s+/).includes('noreferrer')) failures.push(`${prefix}: dashboard destination or new-tab protection is invalid`);
    if (!/github activity dashboard/i.test(state.accessible) || !/opens in a new tab/i.test(state.accessible)) failures.push(`${prefix}: dashboard accessible name is incomplete: ${state.accessible}`);
    if (!state.follows) failures.push(`${prefix}: dashboard CTA does not follow the activity section`);
    if (!state.ctaRect || state.ctaRect.height < 72 || !state.activityRect || state.ctaRect.width < state.activityRect.width * 0.95) failures.push(`${prefix}: dashboard CTA is not visually large/full-width ${JSON.stringify({ activity: state.activityRect, cta: state.ctaRect })}`);
    if (!state.reachable || state.overflow > 1 || state.clipped.length) failures.push(`${prefix}: activity/CTA is clipped, overflowing, or unreachable ${JSON.stringify(state)}`);
  }
  await client.send('Emulation.clearDeviceMetricsOverride');
  return result('BEH-10', failures, ['three headline metrics, reconciled activity graph, subtitle, and dashboard CTA are accessible and responsive across four viewports']);
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const results = [];
  let server;
  let browser;
  let client;
  try {
    server = await startSiteServer(options.root);
    const executable = await discoverBrowser();
    if (!executable) throw new Error('Chrome or Edge executable not found (set CHROME_PATH)');
    browser = await launchBrowser(executable);
    const page = await connectInitialPage(browser.port);
    client = page.client;
    const routes = await discoverPublicRoutes(options.root);
    const behaviorRoutes = [...new Set([...routes, '/projects.html', '/reach-out.html'])].sort();
    const checks = [
      ['BEH-1', () => checkNavVisibility(client, server.baseUrl, behaviorRoutes)],
      ['BEH-2', () => checkInternalNavigation(client, server.baseUrl)],
      ['BEH-3', () => checkTelemetry(client, browser.port, page.targetId, server.baseUrl)],
      ['BEH-5', () => checkReachOut(client, server.baseUrl)],
      ['BEH-6', () => checkContactForm(client, server.baseUrl)],
      ['BEH-9', () => checkHeroFit(client, server.baseUrl)],
      ['BEH-10', () => checkGitHubActivity(client, server.baseUrl)],
      ['PRES-3', () => check31Days(client, server.baseUrl)],
      ['PRES-4', () => checkHamburger(client, server.baseUrl, routes)],
      ['PRES-5', () => checkReveal(client, server.baseUrl)],
      ['PRES-6', () => checkSocialAndClipboard(client, server.baseUrl)],
    ];
    for (const [id, check] of checks) {
      try { results.push(await check()); }
      catch (error) {
        results.push({ id, status: 'FAIL', detail: `Harness completed this check with an error: ${error.message}` });
      }
    }
  } catch (error) {
    const ids = ['BEH-1', 'BEH-2', 'BEH-3', 'BEH-5', 'BEH-6', 'BEH-9', 'BEH-10', 'PRES-3', 'PRES-4', 'PRES-5', 'PRES-6'];
    for (const id of ids) results.push({ id, status: 'FAIL', detail: `Browser harness unavailable: ${error.message}` });
  } finally {
    client?.close();
    await browser?.close().catch(() => {});
    await server?.close().catch(() => {});
  }
  const report = { ok: results.every((entry) => entry.status === 'PASS'), results };
  if (options.json) process.stdout.write(`${JSON.stringify(report)}\n`);
  else for (const entry of results) process.stdout.write(`${entry.status} ${entry.id}: ${entry.detail}\n`);
  process.exitCode = report.ok ? 0 : 1;
}

await main();
