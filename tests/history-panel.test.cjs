const assert = require("node:assert/strict");
const path = require("node:path");
const { test } = require("node:test");
const { chromium } = require("playwright-core");

const asset = path.resolve(__dirname, "../custom_components/notification_dispatcher/history-panel.js");

for (const [layout, width, height] of [["desktop", 1152, 800], ["mobile", 320, 700]]) {
  test(layout + ": scoped history, filters, refresh and account switch", async (t) => {
    const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH });
    t.after(() => browser.close());
    const page = await browser.newPage({ viewport: { width, height }, locale: "de-DE" });
    const errors = [];
    page.on("pageerror", e => errors.push(e.message));
    await page.setContent("<style>html,body{margin:0;height:100%;font:16px system-ui}</style>");
    await page.addScriptTag({ path: asset, type: "module" });
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
        make("Wartung", "sent", { for: ["Mara"] }),
        make("Update", "sent"),
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
    assert.equal(await page.locator("article").count(), 3);
    await page.getByText("FB: @Mara · Übergeben", { exact: true }).waitFor();
    const filter = page.getByRole("combobox", { name: "Status" });
    await filter.selectOption("problems");
    assert.equal(await page.locator("article").count(), 1);
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
}
