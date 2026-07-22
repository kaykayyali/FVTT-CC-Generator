import { existsSync } from "node:fs";
import assert from "node:assert/strict";
import { chromium } from "playwright-core";

const FOUNDRY_URL = process.env.FOUNDRY_URL ?? "http://127.0.0.1:30000";
const MODULE_ID = "fvtt-cc-generator";
const DEFAULT_CHROMIUM =
  "C:/Users/kayka/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH ?? DEFAULT_CHROMIUM;

if (!existsSync(executablePath)) {
  throw new Error(`Chromium executable not found: ${executablePath}`);
}

const browser = await chromium.launch({
  headless: true,
  executablePath,
  args: ["--no-sandbox"],
});

const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
const page = await context.newPage();
const pageErrors = [];
const consoleErrors = [];
const moduleRequestFailures = [];
const moduleLogs = [];

page.on("pageerror", (error) => pageErrors.push(error.stack ?? error.message));
page.on("console", (message) => {
  const text = message.text();
  if (text.includes(MODULE_ID)) moduleLogs.push(`[${message.type()}] ${text}`);
  if (message.type() === "error") consoleErrors.push(text);
});
page.on("requestfailed", (request) => {
  if (request.url().includes(`/modules/${MODULE_ID}/`)) {
    moduleRequestFailures.push(`${request.url()} :: ${request.failure()?.errorText ?? "failed"}`);
  }
});

async function waitForAgentConnections(expectedCount) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    const count = moduleLogs.filter((line) => /Agent connected: fab-agent/i.test(line)).length;
    if (count >= expectedCount) return;
    await page.waitForTimeout(100);
  }
  throw new Error(
    `Expected ${expectedCount} Foundry-to-agent handshake(s), got ` +
    `${moduleLogs.filter((line) => /Agent connected: fab-agent/i.test(line)).length}\n` +
    moduleLogs.join("\n"),
  );
}

async function openDesignerAndAssertConnected() {
  await page.evaluate((moduleId) => game.modules.get(moduleId).api.openDesigner(), MODULE_ID);
  await page.waitForSelector("#fvtt-cc-designer #fab-prompt", {
    state: "visible",
    timeout: 30_000,
  });
  const expectedAgentUrl = await page.evaluate(
    (moduleId) => game.settings.get(moduleId, "agentUrl"),
    MODULE_ID,
  );
  const statusText = await page.locator("#fvtt-cc-designer .fab-status").innerText();
  assert.ok(
    statusText.includes(expectedAgentUrl),
    `Designer status does not show configured agent URL ${expectedAgentUrl}: ${statusText}`,
  );
  assert.doesNotMatch(statusText, /\bPort\s*:/i, `Designer still renders the removed Port field: ${statusText}`);
  await page.waitForFunction(
    () =>
      game.fab_designer?._client?.ws?.readyState === WebSocket.OPEN &&
      game.fab_designer?._client?._helloInfo?.ok === true,
    null,
    { timeout: 30_000 },
  );
}

async function assertModuleReady(label) {
  try {
    await page.waitForFunction(
      (moduleId) => {
        const foundryGame = globalThis.game;
        const module = foundryGame?.modules?.get(moduleId);
        return foundryGame?.ready === true && module?.active === true && Boolean(foundryGame?.fab_designer);
      },
      MODULE_ID,
      { timeout: 60_000 },
    );
  } catch (error) {
    const diagnostic = await page.evaluate((moduleId) => {
      const foundryGame = globalThis.game;
      const module = foundryGame?.modules?.get(moduleId);
      return {
        gameExists: Boolean(foundryGame),
        gameReady: foundryGame?.ready ?? null,
        modulePresent: Boolean(module),
        moduleActive: module?.active ?? null,
        moduleVersion: module?.version ?? null,
        designerReady: Boolean(foundryGame?.fab_designer),
        url: location.href,
      };
    }, MODULE_ID);
    throw new Error(
      `${label}: module did not become ready\n` +
      `${JSON.stringify(diagnostic, null, 2)}\n` +
      `pageErrors=${JSON.stringify(pageErrors, null, 2)}\n` +
      `consoleErrors=${JSON.stringify(consoleErrors, null, 2)}\n` +
      `moduleLogs=${JSON.stringify(moduleLogs, null, 2)}`,
      { cause: error },
    );
  }

  const state = await page.evaluate((moduleId) => {
    const module = game.modules.get(moduleId);
    return {
      active: module?.active ?? false,
      version: module?.version ?? null,
      designerReady: Boolean(game.fab_designer),
      world: game.world?.id ?? null,
      foundryVersion: game.version,
      system: game.system?.id ?? null,
      systemVersion: game.system?.version ?? null,
    };
  }, MODULE_ID);

  assert.equal(state.active, true, `${label}: ${MODULE_ID} is not active`);
  assert.equal(state.designerReady, true, `${label}: game.fab_designer was not registered`);
  return state;
}

function assertNoLoaderFailure(label) {
  const evidence = [...pageErrors, ...consoleErrors].join("\n");
  assert.doesNotMatch(
    evidence,
    /Cannot use import statement outside a module/i,
    `${label}: Foundry parsed an ES module as a classic script:\n${evidence}`,
  );
  assert.equal(
    moduleRequestFailures.length,
    0,
    `${label}: module request failures:\n${moduleRequestFailures.join("\n")}`,
  );
  const moduleSpecificErrors = [...pageErrors, ...consoleErrors].filter((text) =>
    text.toLowerCase().includes(MODULE_ID),
  );
  assert.deepEqual(
    moduleSpecificErrors,
    [],
    `${label}: module-specific browser errors:\n${moduleSpecificErrors.join("\n")}`,
  );
}

try {
  await page.goto(FOUNDRY_URL, { waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForSelector("#join-game-form", { timeout: 30_000 });

  const users = await page.$$eval('select[name="userid"] option', (options) =>
    options.map((option) => ({
      value: option.value,
      label: option.textContent?.trim() ?? "",
      disabled: option.disabled,
    })),
  );
  const user =
    users.find((candidate) => candidate.label === "Gamemaster" && candidate.value && !candidate.disabled) ??
    users.find((candidate) => candidate.value && !candidate.disabled);
  assert.ok(user, "No available Foundry automation user slot");

  await page.selectOption('select[name="userid"]', user.value);
  await page.fill('input[name="password"]', "");
  await page.click('button[name="join"]');
  await page.waitForSelector("#ui-left", { timeout: 60_000 });
  await page.waitForFunction(
    () => globalThis.game?.ready === true && Boolean(globalThis.game?.modules),
    null,
    { timeout: 60_000 },
  );

  const enabledForAcceptance = await page.evaluate(async (moduleId) => {
    const module = game.modules.get(moduleId);
    if (module?.active) return false;
    const configuration = structuredClone(
      game.settings.get("core", "moduleConfiguration") ?? {},
    );
    configuration[moduleId] = true;
    await game.settings.set("core", "moduleConfiguration", configuration);
    return true;
  }, MODULE_ID);
  if (enabledForAcceptance) {
    await page.reload({ waitUntil: "networkidle", timeout: 60_000 });
    await page.waitForSelector("#ui-left", { timeout: 60_000 });
  }

  const initial = await assertModuleReady("initial load");
  assertNoLoaderFailure("initial load");
  await waitForAgentConnections(1);
  await openDesignerAndAssertConnected();
  assertNoLoaderFailure("Designer open");

  pageErrors.length = 0;
  consoleErrors.length = 0;
  moduleRequestFailures.length = 0;
  await page.reload({ waitUntil: "networkidle", timeout: 60_000 });
  await page.waitForSelector("#ui-left", { timeout: 60_000 });
  const reloaded = await assertModuleReady("reload");
  await waitForAgentConnections(2);
  assertNoLoaderFailure("reload startup");

  const connectionLogs = moduleLogs.join("\n");
  assert.doesNotMatch(
    connectionLogs,
    /Agent not reachable/i,
    `Foundry reported the live agent as unreachable:\n${connectionLogs}`,
  );
  assertNoLoaderFailure("final state");

  console.log(JSON.stringify({ initial, reloaded, moduleLogs }, null, 2));
} finally {
  await browser.close();
}
