import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { chromium, request as playwrightRequest } from "playwright";

const baseURL = process.env.HEALTH_TEST_URL || "http://127.0.0.1:5174";
if (!["localhost", "127.0.0.1"].includes(new URL(baseURL).hostname))
  throw Error("Use a dedicated local environment for this test");
const artifacts = process.env.HEALTH_TEST_ARTIFACTS || "/tmp/nasa-health-e2e";
await mkdir(artifacts, { recursive: true });
const api = await playwrightRequest.newContext({ baseURL });
const stamp = Date.now(),
  password = "HealthTest2026!";
async function call(path, { method = "GET", body, token, status = 200 } = {}) {
  const response = await api.fetch("/api/v1" + path, {
    method,
    data: body,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  assert.equal(response.status(), status, await response.text());
  return response.status() === 204 ? null : response.json();
}
async function person(role, isAstronaut, isPhysician) {
  const email = `health.${role}.${stamp}@example.com`;
  const user = await call("/users/", {
    method: "POST",
    body: {
      name: `Test ${role}`,
      email,
      password,
      password_confirmation: password,
      is_astronaut: isAstronaut,
      is_physician: isPhysician,
    },
  });
  const login = await call("/auth/login", {
    method: "POST",
    body: { email, password },
  });
  return { ...user, email, token: login.access_token };
}
const astronaut = await person("astronaut", true, false),
  doctor = await person("doctor", false, true),
  admin = await person("admin", false, true),
  other = await person("other", true, false);
const mission = await call("/missions", {
  method: "POST",
  token: admin.token,
  status: 201,
  body: {
    name: `Monitoring test ${stamp}`,
    planned_launch_at: new Date(Date.now() + 30 * 86400000).toISOString(),
  },
});
for (const [user, role] of [
  [astronaut, "astronaut"],
  [doctor, "flight_surgeon"],
])
  await call(`/missions/${mission.id}/members`, {
    method: "POST",
    token: admin.token,
    status: 201,
    body: { user_id: user.id, role },
  });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
    : {}),
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }),
  errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.setDefaultTimeout(15000);
async function login(user) {
  await page.goto(baseURL);
  await page.getByLabel("Email", { exact: true }).fill(user.email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in to the platform" }).click();
}
async function waitUntil(predicate) {
  for (let i = 0; i < 100; i++) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw Error("Timed out waiting for the update");
}
const card = (name) =>
  page.locator(".health-card").filter({
    has: page.locator("span").filter({ hasText: new RegExp(`^${name}$`) }),
  }).locator(".health-card-main");
async function saveHeartRate(value, collectedAt) {
  await page
    .getByRole("button", { name: "Record measurement", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Collection time").fill(collectedAt);
  await dialog.getByLabel("Value (bpm)").fill(String(value));
  await dialog
    .getByLabel("Note (optional)")
    .fill("Fictional test measurement");
  await dialog
    .getByRole("button", { name: "Save measurement", exact: true })
    .click();
  await dialog.waitFor({ state: "hidden" });
  await page
    .getByRole("status")
    .filter({ hasText: "Loading history" })
    .waitFor({ state: "hidden" });
}
const local = (value) =>
  new Date(value - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
try {
  await login(astronaut);
  await page
    .getByRole("heading", { name: "Health monitoring", exact: true })
    .waitFor();
  await waitUntil(
    async () => (await page.locator(".health-card").count()) === 12,
  );
  assert.equal(await page.locator(".body-hotspot").count(), 4);
  await waitUntil(
    async () =>
      await page
        .getByRole("button", { name: "Record measurement", exact: true })
        .isVisible(),
  );
  assert.match(await card("Heart rate").innerText(), /No data/);
  await saveHeartRate(72, local(Date.now() - 3600000));
  await waitUntil(async () =>
    /72/.test(await card("Heart rate").innerText()),
  );
  await saveHeartRate(65, local(Date.now() - 2 * 86400000));
  assert.match(await card("Heart rate").innerText(), /72/);
  const values = await page
    .locator(".health-detail tbody tr td:nth-child(2)")
    .allTextContents();
  assert.deepEqual(
    values.map((value) => value.trim()),
    ["65 bpm", "72 bpm"],
  );
  await page.getByRole("button", { name: "24 hours", exact: true }).click();
  await waitUntil(
    async () => (await page.locator(".health-detail tbody tr").count()) === 1,
  );
  await card("Changes in attention").focus();
  await page.keyboard.press("Enter");
  assert.equal(
    await card("Changes in attention").getAttribute("aria-pressed"),
    "true",
  );
  await page
    .getByRole("button", { name: "Record measurement", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Compared with your individual baseline")
    .selectOption("usual");
  await page
    .getByRole("dialog")
    .getByLabel("Note (optional)")
    .fill("Usual attention in test");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save measurement", exact: true })
    .click();
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  await page.locator(".health-timeline li").first().waitFor();
  await card("Level of consciousness").click();
  await waitUntil(
    async () =>
      await page
        .getByRole("heading", { name: "Level of consciousness", exact: true })
        .isVisible(),
  );
  assert.equal(
    await page
      .getByRole("button", { name: "Record measurement", exact: true })
      .count(),
    0,
  );
  await card("Blood pressure").click();
  await page
    .getByRole("button", { name: "Record measurement", exact: true })
    .click();
  await page.getByRole("dialog").getByLabel("Systolic (mmHg)").fill("120");
  await page.getByRole("dialog").getByLabel("Diastolic (mmHg)").fill("80");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save measurement", exact: true })
    .click();
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  await waitUntil(
    async () => (await page.locator(".recharts-line").count()) === 2,
  );
  await card("Sleep duration").click();
  await page
    .getByRole("button", { name: "Record measurement", exact: true })
    .click();
  await page.getByRole("dialog").getByLabel("Hours of sleep").fill("7");
  await page.getByRole("dialog").getByLabel("Additional minutes").fill("30");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save measurement", exact: true })
    .click();
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  await waitUntil(async () =>
    /7h 30min/.test(await card("Sleep duration").innerText()),
  );
  await page
    .getByRole("button", { name: "Record measurement", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("Enter sleep start and end times")
    .check();
  await page
    .getByRole("dialog")
    .getByLabel("Collection time")
    .fill(local(Date.now() - 2 * 86400000));
  await page
    .getByRole("dialog")
    .getByLabel("Sleep start", {exact:true})
    .fill(local(Date.now() - 2 * 86400000 - 8 * 3600000));
  await page
    .getByRole("dialog")
    .getByLabel("Sleep end", {exact:true})
    .fill(local(Date.now() - 2 * 86400000));
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save measurement", exact: true })
    .click();
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  await waitUntil(async () =>
    /7h 30min/.test(await card("Sleep duration").innerText()),
  );
  for (const [name, value] of [
    ["Blood glucose (blood sugar)", "95"],
    ["Respiratory rate", "16"],
    ["Oxygen saturation", "98"],
    ["Body temperature", "36.5"],
    ["Sleep quality", "4"],
    ["Fatigue", "3"],
    ["Mood", "4"],
  ]) {
    await card(name).click();
    await page
      .getByRole("button", { name: "Record measurement", exact: true })
      .click();
    const input = page.getByRole("dialog").locator('[name="value"]');
    if ((await input.evaluate((element) => element.tagName)) === "SELECT")
      await input.selectOption(value);
    else await input.fill(value);
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Save measurement", exact: true })
      .click();
    await page.getByRole("dialog").waitFor({ state: "hidden" });
  }
  for (const button of await page.locator(".health-card").all()) {
    await button.locator(".health-card-main").click();
    assert.equal(await button.locator(".health-card-main").getAttribute("aria-pressed"), "true");
    assert.equal(
      await page.locator('.body-hotspot[aria-pressed="true"]').count(),
      ["heart_rate", "body_temperature", "blood_pressure", "respiratory_rate"].includes(await button.getAttribute("data-indicator")) ? 1 : 0,
    );
  }
  await card("Heart rate").click();
  await waitUntil(
    async () => (await page.locator(".health-detail tbody tr").count()) === 1,
  );
  await page.screenshot({ path: `${artifacts}/desktop.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await waitUntil(
    async () =>
      (await page.locator(".health-card").first().boundingBox()) !== null,
  );
  const bodyBox = await page.locator(".health-body").boundingBox(),
    cardBox = await page.locator(".health-card").first().boundingBox();
  assert.ok(cardBox.y >= bodyBox.y + bodyBox.height - 1);
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  );
  await page.screenshot({ path: `${artifacts}/mobile.png`, fullPage: true });
  const path = `/health/astronauts/${astronaut.id}`;
  await call(path + "/summary", { token: other.token, status: 403 });
  await call(path + "/history?indicator=heart_rate", {
    token: other.token,
    status: 403,
  });
  await call(path + "/observations", {
    method: "POST",
    token: astronaut.token,
    status: 403,
    body: {
      indicator: "consciousness",
      category: "alert",
      collected_at: new Date(Date.now() - 60000).toISOString(),
      source: "manual_measurement",
      mission_id: mission.id,
    },
  });
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("heading", { name: "Sign in", exact: true }).waitFor();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(doctor);
  await page
    .getByRole("button", { name: "Health monitoring", exact: true })
    .click();
  await page
    .getByLabel("Mission", { exact: true })
    .selectOption(String(mission.id));
  await page
    .getByLabel("Astronaut", { exact: true })
    .selectOption(String(astronaut.id));
  await card("Level of consciousness").click();
  await waitUntil(
    async () =>
      await page
        .getByRole("button", { name: "Record measurement", exact: true })
        .isVisible(),
  );
  await page
    .getByRole("button", { name: "Record measurement", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel("AVPU assessment")
    .selectOption("alert");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Save measurement", exact: true })
    .click();
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  await waitUntil(async () =>
    /Alert/.test(await card("Level of consciousness").innerText()),
  );
  const complete = await call(`/health/astronauts/${astronaut.id}/summary`, {
    token: astronaut.token,
  });
  assert.equal(
    complete.indicators.filter((indicator) => indicator.latest !== null).length,
    12,
  );
  assert.deepEqual(errors, []);
  console.log(
    JSON.stringify(
      {
        passed: true,
        checks: [
          "astronaut_home",
          "4_hotspots_and_12_cards",
          "keyboard_selection",
          "manual_registration_all_12_indicators",
          "blood_pressure_two_series",
          "sleep_hours_minutes_and_session",
          "backdated_collection",
          "24_hour_filter",
          "categorical_timeline",
          "avpu_assessor",
          "patient_isolation",
          "mobile_layout",
          "no_runtime_errors",
        ],
        artifacts,
      },
      null,
      2,
    ),
  );
} catch (error) {
  console.error(
    JSON.stringify(
      {
        runtimeErrors: errors,
        url: page.url(),
        body: await page.locator("body").innerText(),
      },
      null,
      2,
    ),
  );
  await page.screenshot({ path: `${artifacts}/failure.png`, fullPage: true });
  throw error;
} finally {
  await browser.close();
  await api.dispose();
}
