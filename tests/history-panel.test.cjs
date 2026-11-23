const assert = require("node:assert/strict");
const path = require("node:path");
const { test } = require("node:test");
const { chromium } = require("playwright-core");
const mdi = require("@mdi/js");

const assets = path.resolve(__dirname, "../custom_components/notification_dispatcher");
async function openPanel(t, width, height) {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH });
  t.after(() => browser.close());
  const page = await browser.newPage({ viewport: { width, height }, locale: "de-DE" });
  const names = ("plus close trash-can-outline pencil-outline earth calendar-week-outline infinity clock-check-outline " +
    "home-outline information-outline alert-outline clock-outline alert-octagon-outline lock-outline check refresh " +
    "history calendar-clock-outline filter-variant chevron-down email-outline menu").split(" ");
  const paths = Object.fromEntries(names.map(name => {
    const value = mdi["mdi" + name.split("-").map(s => s[0].toUpperCase() + s.slice(1)).join("")];
    assert.ok(value, "Unknown Material Design icon " + name);
    return [name, value];
  }));
  await page.addInitScript(paths => {
    class HaIcon extends HTMLElement {
      static get observedAttributes() { return ["icon"]; }
      connectedCallback() { this.draw(); }
      attributeChangedCallback() { this.draw(); }
      draw() {
        const path = paths[(this.getAttribute("icon") || "").replace("mdi:", "")];
        if (path) (this.shadowRoot || this.attachShadow({mode:"open"})).innerHTML =
          '<svg aria-hidden="true" viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="' + path + '"/></svg>';
      }
    }
    customElements.define("ha-icon", HaIcon);
    customElements.define("ha-menu-button", class extends HTMLElement {
      connectedCallback() { this.innerHTML='<ha-icon style="width:22px;height:22px;display:block" icon="mdi:menu"></ha-icon>'; }
    });
  }, paths);
  await page.route("http://dispatcher.test/**", route => {
    const name = new URL(route.request().url()).pathname.split("/").pop();
    if (["history-panel.js", "availability.js", "week-picker.js", "panel-ui.js"].includes(name)) {
      return route.fulfill({ path: path.join(assets, name), contentType: "text/javascript" });
    }
    if (name === "icon.png") return route.fulfill({path:path.join(assets,"brand",name),contentType:"image/png"});
    return route.fulfill({ contentType: "text/html", body: '<style>html,body{margin:0;height:100%;font:16px system-ui}</style><script type="module" src="/history-panel.js"></script>' });
  });
  await page.goto("http://dispatcher.test/");
  await page.evaluate(() => customElements.whenDefined("notification-dispatcher-history").then(() => true));
  return page;
}

async function darkTheme(page, enabled) {
  await page.evaluate(on => {
    document.querySelector("#night")?.remove();
    if (!on) return;
    const el=document.createElement("style"); el.id="night";
    el.textContent=":root{color-scheme:dark;--primary-background-color:#141819;--card-background-color:#1e2425;--primary-text-color:#edf2f3;--secondary-text-color:#b0bec1;--divider-color:#3b4446;--primary-color:#50c3d0;--warning-color:#ebad54;--success-color:#60b990;--error-color:#f08080}";
    document.head.append(el);
  }, enabled);
}
async function shot(page, name) {
  if (process.env.HISTORY_SCREENSHOTS) await page.screenshot({ path: path.join(process.env.HISTORY_SCREENSHOTS, name + ".png") });
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
    await page.getByRole("heading", {name:"Benachrichtigen"}).waitFor();
    assert.ok(await page.locator("img.brand").evaluate(img => img.complete && img.naturalWidth > 0));
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
    await page.getByRole("radiogroup", { name: "Zustellzeiten" }).waitFor();
    assert.equal(await save.isDisabled(), true);
    const monday = page.getByRole("button", {name:"Montag: 08:00 – 22:00",exact:true});
    await monday.waitFor();
    await page.getByRole("button",{name:"Samstag: Kein Zeitfenster"}).waitFor();
    await darkTheme(page, true);
    await shot(page, "benachrichtigen-" + layout);
    await page.getByRole("radio",{name:"Rund um die Uhr"}).check();
    assert.equal(await monday.isVisible(), false);
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
    await page.getByRole("radio",{name:"Wochenplan",exact:true}).check();
    await monday.click();
    const dialog = page.getByRole("dialog");
    await dialog.getByRole("button",{name:"Donnerstag",exact:true}).click();
    await dialog.getByRole("combobox",{name:"Von · Stunde"}).selectOption("21");
    await dialog.getByRole("combobox",{name:"Bis · Stunde"}).selectOption("06");
    await dialog.getByLabel("Bis · Minute").selectOption("37");
    await dialog.getByText("Endet am Folgetag.").waitFor();
    await dialog.getByText("Ersetzt die bisherigen Zeiten für Donnerstag.").waitFor();
    await shot(page, "tagespicker-" + layout);
    assert.ok(await dialog.evaluate(n=>n.getBoundingClientRect().left>=0 && n.getBoundingClientRect().right<=innerWidth+1 && n.scrollWidth<=n.clientWidth+1));
    await dialog.getByRole("button",{name:"Übernehmen"}).click();
    await page.getByRole("button",{name:"Zeitfenster hinzufügen",exact:true}).click();
    assert.ok(await dialog.getByRole("button",{name:"Übernehmen"}).isDisabled());
    await dialog.getByLabel("Tagesauswahl").selectOption("every");
    await dialog.getByRole("button",{name:"Abbrechen"}).click();
    await page.getByRole("button",{name:"Samstag: Kein Zeitfenster"}).waitFor();
    await page.getByRole("button",{name:"Zeitfenster hinzufügen",exact:true}).click();
    await dialog.getByLabel("Tagesauswahl").selectOption("weekend");
    await dialog.getByLabel("Ganztägig").check();
    await dialog.getByRole("button",{name:"Übernehmen"}).click();
    await page.getByRole("button",{name:"Samstag: Ganztägig"}).waitFor();
    await darkTheme(page, false);
    await shot(page, "wochenplan-licht-" + layout);
    await page.getByRole("button",{name:"Zeitfenster bearbeiten: Sa – So"}).click();
    await dialog.getByRole("button",{name:"Zeitfenster entfernen"}).click();
    await page.getByRole("button",{name:"Samstag: Kein Zeitfenster"}).waitFor();
    assert.equal(await page.evaluate(() => updates.length), 1);
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
    assert.deepEqual(request.settings.day_windows,{mon:"21:00-06:37",tue:"08:00-22:00",wed:"08:00-22:00",thu:"21:00-06:37",fri:"08:00-22:00"});
    assert.equal(request.settings.weekend_window, "");
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
