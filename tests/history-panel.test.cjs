const assert = require("node:assert/strict");
const path = require("node:path");
const { test } = require("node:test");
const { chromium } = require("playwright-core");

const assets = path.resolve(__dirname, "../custom_components/notification_dispatcher");
async function openPanel(t, width, height) {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width, height }, locale: "de-DE" });
  await page.route("http://dispatcher.test/**", route => {
    const name = new URL(route.request().url()).pathname.split("/").pop();
    if (["history-panel.js", "availability.js"].includes(name)) {
      return route.fulfill({ path: path.join(assets, name), contentType: "text/javascript" });
    }
    return route.fulfill({ contentType: "text/html", body: '<style>html,body{margin:0;height:100%;font:16px system-ui}</style><script type="module" src="/history-panel.js"></script>' });
  });
  await page.goto("http://dispatcher.test/");
  await page.evaluate(() => customElements.whenDefined("notification-dispatcher-history").then(() => true));
  return page;
}

for (const [layout, width, height] of [["desktop", 1152, 800], ["mobile", 320, 700]]) {
  test(layout + ": scoped history, filters, refresh and account switch", async (t) => {
    const page = await openPanel(t, width, height);
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.evaluate(async () => {
      await customElements.whenDefined("notification-dispatcher-history");
      const panel = document.createElement("notification-dispatcher-history");
      document.body.append(panel);
      const make = (title, status, rest) => ({
        timestamp: "2026-11-22T18:42:00+00:00", type: "info", title,
        message: "Hohe Luftfeuchtigkeit im Büro.",
        routes: [{ status, reason: null, fallback: null, for: [], ...rest }],
      });
      window.items = [
        make("Büro", "blocked", { reason: "person_not_home", fallback: "sent" }),
        make("Wartung", "sent", { for: ["Mara"], read: true }),
        make("Update", "sent", { due: "2026-11-22T19:12:00+00:00" }),
        make("Erinnerung", "sent", { repeat: "blocked", repeat_reason: "dnd_active" }),
      ];
      window.session = (id, fetch) => ({
        user: { id }, connection: {}, language: "de", config: { time_zone: "Europe/Berlin" },
        callWS: (msg) => {
          if (Object.keys(msg).length !== 1 || msg.type !== "notification_dispatcher/history") {
            throw Error("Unexpected WebSocket request");
          }
          return fetch();
        },
      });
      window.panel = panel;
      panel.hass = session("linda", async () => items);
    });
    await page.getByText("An Fallback übergeben", { exact: false }).waitFor();
    assert.equal(await page.locator("article").count(), 4);
    await page.getByText("Gelesen", { exact: true }).waitFor();
    await page.getByText("Erneut erinnern um 20:12", { exact: true }).waitFor();
    await page.getByText("FB: @Mara · Übergeben", { exact: true }).waitFor();
    const filter = page.getByRole("combobox", { name: "Status" });
    await filter.selectOption("problems");
    assert.equal(await page.locator("article").count(), 2);
    await page.getByText("Erinnerung nicht zugestellt · Nicht stören: Ruhezeit aktiv", { exact: true }).waitFor();
    await page.getByText("keine Anwesenheit erkannt", { exact: false }).waitFor();
    await filter.selectOption("forwarded");
    assert.equal(await page.locator("article").count(), 2);
    await filter.selectOption("all");
    if (process.env.HISTORY_SCREENSHOTS) {
      await page.screenshot({ path: path.join(process.env.HISTORY_SCREENSHOTS, layout + ".png") });
    }
    await page.evaluate(() => {
      items[0].title = "Z".repeat(100);
      items[0].message = "<b>Nur Text</b>";
    });
    await page.getByRole("button", { name: "Aktualisieren" }).click();
    await page.getByText("<b>Nur Text</b>", { exact: true }).waitFor();
    assert.equal(await page.locator("article b").count(), 0);
    assert.ok(await page.evaluate(() => {
      const limit = innerWidth;
      return [...panel.shadowRoot.querySelectorAll("article, strong, p, time, select")]
        .every(n => n.getBoundingClientRect().right <= limit + 1 && n.scrollWidth <= n.clientWidth + 1);
    }));
    assert.ok(await page.evaluate(() => {
      panel.hass = session("johannes", () => new Promise(resolve => { window.late = resolve; }));
      return !panel.shadowRoot.textContent.includes("<b>Nur Text</b>");
    }));
    await page.evaluate(() => {
      panel.hass = session("mara", async () => []);
      late(items);
    });
    await page.getByText("Noch keine Nachrichten für dich.", { exact: true }).waitFor();
    assert.equal(await page.locator("article").count(), 0);
    await page.evaluate(() => { panel.hass = session("mara", () => Promise.reject(Error("offline"))); });
    await page.getByText("Verlauf konnte nicht geladen werden.", { exact: true }).waitFor();
    assert.deepEqual(errors, []);
  });

  test(layout + ": personal availability, saving, conflicts and account isolation", async t => {
    const page = await openPanel(t, width, height);
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.evaluate(() => {
      window.panel = document.createElement("notification-dispatcher-history");
      document.body.append(panel);
      window.current = { state: "ready", revision: "r1", quiet_window: "22:00-07:00", quiet_in_24h: true,
        settings: { always_notify: false, only_when_home: false, weekday_window: "08:00-22:00", weekend_window: "", enabled_types: ["info", "warning"] } };
      window.updates = [];
      window.session = (id, language = "de") => ({ user: { id }, connection: {}, language, config: { time_zone: "Europe/Berlin" },
        callWS: async msg => {
          if (msg.type.endsWith("/history")) return [];
          if (msg.type.endsWith("/preferences")) return id === "linda" ? structuredClone(current) : { state: "unlinked" };
          updates.push(msg);
          if (window.fail === "delay") return new Promise(resolve => { window.finish = resolve; });
          if (window.fail) throw { code: window.fail };
          current = { ...current, revision: "r" + (updates.length + 1), settings: msg.settings,
            quiet_window: msg.clear_quiet_hours ? "" : current.quiet_window };
          return structuredClone(current);
        } });
      panel.hass = session("linda");
    });
    const tab = page.getByRole("tab", { name: "Meine Erreichbarkeit" });
    await tab.click();
    const save = page.getByRole("button", { name: "Speichern", exact: true });
    await page.getByRole("group", { name: "Zustellzeiten" }).waitFor();
    assert.equal(await save.isDisabled(), true);
    assert.equal(await page.locator("#weekday-start").inputValue(), "08:00");
    assert.equal(await page.locator("#weekend-start").isVisible(), false);
    await page.getByLabel("Rund um die Uhr (24/7)").check();
    assert.equal(await page.locator("#weekday-start").isVisible(), false);
    await page.getByLabel("Nur wenn zuhause").check();
    await page.getByRole("tab", { name: "Verlauf", exact: true }).click();
    await tab.click();
    assert.ok(await page.getByLabel("Nur wenn zuhause").isChecked());
    await save.click();
    await page.getByText("Erreichbarkeit gespeichert.").waitFor();
    let request = await page.evaluate(() => updates.at(-1));
    assert.deepEqual(Object.keys(request).sort(), ["revision", "settings", "type"]);
    assert.equal(request.settings.always_notify, true);
    assert.equal(request.settings.weekday_window, "08:00-22:00");
    await page.getByLabel("Zeitfenster", { exact: true }).check();
    await page.getByRole("checkbox", { name: "Wochenende", exact: true }).check();
    await page.locator("#weekday-start").fill("");
    await save.click();
    assert.equal(await page.evaluate(() => updates.length), 1);
    await page.locator("#weekday-start").fill("21:00");
    await page.locator("#weekday-end").fill("06:30");
    await page.getByLabel("Warnung", { exact: true }).uncheck();
    await page.getByLabel("Erinnerung", { exact: true }).check();
    await page.getByLabel("Diese Ruhezeit aufheben").check();
    if (process.env.HISTORY_SCREENSHOTS) {
      await page.screenshot({ path: path.join(process.env.HISTORY_SCREENSHOTS, "availability-" + layout + ".png") });
    }
    assert.ok(await page.evaluate(() => {
      const form = panel.shadowRoot.querySelector("#availability").shadowRoot;
      return [...form.querySelectorAll("label,input,button,fieldset")].filter(n => n.offsetWidth)
        .every(n => n.getBoundingClientRect().right <= innerWidth + 1);
    }));
    await page.evaluate(() => { window.fail = "offline"; });
    await save.click();
    await page.getByText("Speichern fehlgeschlagen.", { exact: false }).waitFor();
    await page.evaluate(() => { window.fail = null; });
    await save.click();
    await page.getByText("Erreichbarkeit gespeichert.").waitFor();
    request = await page.evaluate(() => updates.at(-1));
    assert.equal(request.clear_quiet_hours, true);
    assert.equal(request.settings.weekday_window, "21:00-06:30");
    assert.equal(request.settings.weekend_window, "09:00-22:00");
    assert.deepEqual(request.settings.enabled_types, ["info", "reminder"]);
    await page.getByLabel("Nur wenn zuhause").uncheck();
    await page.evaluate(() => { window.fail = "preferences_changed"; });
    await save.click();
    await page.getByText("Deine Einstellungen wurden inzwischen geändert.", { exact: false }).waitFor();
    assert.equal(await save.isDisabled(), true);
    await page.getByRole("button", { name: "Neu laden" }).click();
    assert.ok(await page.getByLabel("Nur wenn zuhause").isChecked());
    await page.evaluate(() => { window.fail = "delay"; });
    await page.getByLabel("Info", { exact: true }).uncheck();
    await save.click();
    await page.waitForFunction(() => typeof window.finish === "function");
    await page.evaluate(() => { panel.hass = session("mara", "en"); finish(current); });
    await page.getByRole("tab", { name: "My availability" }).click();
    await page.getByText("Your HA account is not linked", { exact: false }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Save", exact: true }).count(), 0);
    await page.getByRole("tab", { name: "My availability" }).press("Home");
    assert.equal(await page.getByRole("tab", { name: "History", exact: true }).getAttribute("aria-selected"), "true");
    assert.deepEqual(errors, []);
  });
}
