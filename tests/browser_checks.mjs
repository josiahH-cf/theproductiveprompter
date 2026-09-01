#!/usr/bin/env node

/**
 * Dependency-free browser behavior checks for the static site.
 *
 * Usage:
 *   node tests/browser_checks.mjs --root <repository> --json
 *
 * The harness deliberately uses only Node built-ins and Chrome/Edge's DevTools
 * protocol.  It serves the repository from an ephemeral loopback origin so
 * root-relative links, fetch, form validation, and new-tab behavior are real.
 */

import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, readFile, readdir, rm, stat } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, extname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const PLACEHOLDER = 'PASTE_FORM_FORWARDING_ENDPOINT_HERE';
const FORM_ENDPOINT = 'https://form.test/contact';
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
  let endpointOverride = null;
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
      let body = await readFile(diskPath);
      const type = mimeType(diskPath);
      if (endpointOverride && /(?:html|javascript)/.test(type)) {
        body = Buffer.from(body.toString('utf8').split(PLACEHOLDER).join(endpointOverride));
      }
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
    setEndpoint(value) { endpointOverride = value; },
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

async function checkContactForm(client, server, baseUrl) {
  const failures = [];
  server.setEndpoint(null);
  await navigate(client, `${baseUrl}/reach-out.html?form-test=placeholder`);
  const placeholder = await evaluate(client, `(() => {
    const form = document.querySelector('#contactForm');
    const button = form?.querySelector('button[type="submit"], input[type="submit"]');
    const live = document.querySelector('[aria-live]');
    return { form: !!form, disabled: !!button?.disabled, status: live?.textContent.replace(/\\s+/g, ' ').trim() || '',
      statusState: live?.dataset.state || '', emailFallback: !!live?.querySelector('a[href^="mailto:"]') };
  })()`);
  if (!placeholder.form) return result('BEH-6', ['contact form missing; runtime states cannot be tested']);
  const fallbackText = 'The contact form is not configured yet. Email me directly instead.';
  if (!placeholder.disabled) failures.push('placeholder endpoint did not disable submit');
  if (placeholder.status !== fallbackText) failures.push(`placeholder status mismatch: ${placeholder.status || '(missing)'}`);
  if (placeholder.statusState !== 'fallback') failures.push(`placeholder status state mismatch: ${placeholder.statusState || '(missing)'}`);
  if (!placeholder.emailFallback) failures.push('placeholder status lacks email fallback link');

  server.setEndpoint(FORM_ENDPOINT);
  await client.send('Fetch.enable', { patterns: [{ urlPattern: 'https://form.test/*', requestStage: 'Request' }] });
  let mode = 'success';
  let requests = [];
  const stop = client.on('Fetch.requestPaused', (event) => {
    requests.push(event.request);
    setTimeout(() => {
      if (mode === 'reject') client.send('Fetch.failRequest', { requestId: event.requestId, errorReason: 'Failed' }).catch(() => {});
      else client.send('Fetch.fulfillRequest', {
        requestId: event.requestId, responseCode: mode === 'success' ? 204 : 500,
        responseHeaders: [{ name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Content-Type', value: 'application/json' }],
        body: mode === 'success' ? '' : Buffer.from('{"error":"test"}').toString('base64'),
      }).catch(() => {});
    }, 250);
  });

  const loadConfigured = async (caseName) => {
    requests = [];
    await navigate(client, `${baseUrl}/reach-out.html?form-test=${caseName}-${Date.now()}`);
    return evaluate(client, `!document.querySelector('#contactForm button[type="submit"], #contactForm input[type="submit"]')?.disabled`);
  };
  const submit = () => evaluate(client, `(() => {
    const form = document.querySelector('#contactForm');
    form.elements.name.value = 'Browser Tester';
    form.elements.email.value = 'browser@example.com';
    form.elements.message.value = 'Adversarial browser message';
    form.requestSubmit();
  })()`);
  const formState = () => evaluate(client, `(() => {
    const form = document.querySelector('#contactForm');
    const button = form.querySelector('button[type="submit"], input[type="submit"]');
    const live = document.querySelector('[aria-live]');
    return { disabled: button.disabled, status: live?.textContent.replace(/\\s+/g, ' ').trim() || '', statusState: live?.dataset.state || '',
      busy: form.getAttribute('aria-busy'), pendingClass: button.classList.contains('is-pending'),
      mail: !!live?.querySelector('a[href^="mailto:"]'), name: form.elements.name.value,
      email: form.elements.email.value, message: form.elements.message.value };
  })()`);

  mode = 'success';
  if (!await loadConfigured('success')) failures.push('valid HTTPS endpoint did not enable submit');
  await submit();
  await delay(50);
  let state = await formState();
  if (state.status !== 'Sending your message…' || state.statusState !== 'pending' || state.busy !== 'true' || !state.pendingClass || !state.disabled) failures.push(`pending state incorrect: ${JSON.stringify(state)}`);
  await evaluate(client, `document.querySelector('#contactForm').requestSubmit()`);
  await delay(50);
  if (requests.length !== 1) failures.push(`repeat submit produced ${requests.length} requests (expected 1)`);
  state = await until(formState, (value) => value.status === 'Thanks for reaching out. Your message was sent.');
  if (state.status !== 'Thanks for reaching out. Your message was sent.') failures.push(`2xx success state missing: ${state.status}`);
  if (state.statusState !== 'success' || state.busy || state.pendingClass || state.disabled) failures.push(`2xx success state semantics incorrect: ${JSON.stringify(state)}`);
  if (state.name || state.email || state.message) failures.push('2xx success did not reset the form');
  const request = requests[0];
  if (!request || request.method !== 'POST') failures.push('configured form did not issue one POST');
  const accept = request && Object.entries(request.headers || {}).find(([name]) => name.toLowerCase() === 'accept')?.[1];
  if (accept !== 'application/json') failures.push(`POST Accept header mismatch: ${accept || '(missing)'}`);
  for (const value of ['Browser Tester', 'browser@example.com', 'Adversarial browser message']) if (!request?.postData?.includes(value)) failures.push(`POST body missing ${value}`);

  mode = 'server-error';
  await loadConfigured('500');
  await submit();
  state = await until(formState, (value) => value.status.startsWith("I couldn't send your message."));
  if (state.status !== "I couldn't send your message. Please try again or email me directly." || state.statusState !== 'error' || state.busy || state.pendingClass || state.disabled || !state.mail) failures.push(`500 error state/fallback incorrect: ${JSON.stringify(state)}`);
  if (state.name !== 'Browser Tester') failures.push('500 response incorrectly reset the form');

  mode = 'reject';
  await loadConfigured('reject');
  await submit();
  state = await until(formState, (value) => value.status.startsWith("I couldn't send your message."));
  if (state.status !== "I couldn't send your message. Please try again or email me directly." || state.statusState !== 'error' || state.busy || state.pendingClass || state.disabled || !state.mail) failures.push(`network rejection state/fallback incorrect: ${JSON.stringify(state)}`);

  mode = 'success';
  await loadConfigured('validation');
  await evaluate(client, `(() => { const form = document.querySelector('#contactForm'); form.elements.name.value=''; form.elements.email.value='invalid'; form.elements.message.value=''; form.requestSubmit(); })()`);
  await delay(150);
  if (requests.length) failures.push('invalid form issued a network request');

  stop();
  await client.send('Fetch.disable');
  server.setEndpoint(null);
  return result('BEH-6', failures, ['placeholder, validation, pending, 2xx, 5xx, and rejected-network states passed']);
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
  await client.send('Page.addScriptToEvaluateOnNewDocument', { source: `
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
      writeText(value) { window.__browserHarnessCopied = String(value); return Promise.resolve(); }
    }});
  ` });
  await client.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
  await navigate(client, `${baseUrl}/index.html?clipboard-test=desktop`);
  const desktop = await evaluate(client, `(async () => {
    const sidebar = document.querySelector('.social-sidebar'); const email = document.querySelector('#emailLink');
    const external = [...(sidebar?.querySelectorAll('a[href^="http"]') || [])];
    email?.click(); await new Promise(r => setTimeout(r, 50));
    return { sidebar: !!sidebar, visible: sidebar && getComputedStyle(sidebar).display !== 'none', email: email?.getAttribute('href'),
      copied: window.__browserHarnessCopied || '', tooltip: document.body.innerText.includes('Email copied!'),
      safeExternal: external.length >= 2 && external.every(a => a.target === '_blank' && a.rel.split(/\\s+/).includes('noopener') && a.rel.split(/\\s+/).includes('noreferrer')) };
  })()`);
  if (!desktop.sidebar || !desktop.visible) failures.push('desktop social sidebar missing or hidden');
  if (desktop.email !== `mailto:${EMAIL}` || desktop.copied !== EMAIL || !desktop.tooltip) failures.push(`desktop email clipboard behavior failed: ${JSON.stringify(desktop)}`);
  if (!desktop.safeExternal) failures.push('social external links lack safe new-tab attributes');
  await client.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await navigate(client, `${baseUrl}/index.html?clipboard-test=mobile`);
  const mobileHidden = await evaluate(client, `(() => { const sidebar = document.querySelector('.social-sidebar'); return !!sidebar && getComputedStyle(sidebar).display === 'none'; })()`);
  if (!mobileHidden) failures.push('social sidebar is not hidden at mobile width');
  await client.send('Emulation.clearDeviceMetricsOverride');
  return result('PRES-6', failures, ['desktop sidebar links/copy tooltip and mobile hiding passed']);
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
      ['BEH-6', () => checkContactForm(client, server, server.baseUrl)],
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
    const ids = ['BEH-1', 'BEH-2', 'BEH-3', 'BEH-5', 'BEH-6', 'PRES-3', 'PRES-4', 'PRES-5', 'PRES-6'];
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
