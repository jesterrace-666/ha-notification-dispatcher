import "./availability.js";
import { controls, glyph } from "./panel-ui.js";

const words = {
  de: {
    title: "Benachrichtigen", refresh: "Aktualisieren", filter: "Status",
    one: "Nachricht", many: "Nachrichten", day_disabled: "Dieser Tag ist im Wochenplan frei",
    outside_day_window: "Außerhalb des persönlichen Zeitfensters",
    history: "Verlauf", availability: "Meine Erreichbarkeit",
    all: "Alle Vorgänge", problems: "Nicht zugestellt", forwarded: "Fallback",
    loading: "Verlauf wird geladen …", empty: "Noch keine Nachrichten für dich.",
    noMatch: "Keine passenden Nachrichten.", error: "Verlauf konnte nicht geladen werden.",
    info: "Info", warning: "Warnung", critical: "Kritisch", reminder: "Erinnerung",
    sent: "Übergeben", partial: "Teilweise übergeben", blocked: "Nicht zugestellt",
    failed: "Versand fehlgeschlagen", not_attempted: "Versand abgebrochen",
    person_not_home: "Nur zuhause: keine Anwesenheit erkannt",
    weekday_disabled: "Werktags ist keine Zustellung aktiviert",
    weekend_disabled: "Am Wochenende ist keine Zustellung aktiviert",
    outside_weekday_window: "Außerhalb des Werktag-Zeitfensters",
    outside_weekend_window: "Außerhalb des Wochenend-Zeitfensters",
    dnd_active: "Nicht stören: Ruhezeit aktiv", type_not_enabled: "Nachrichtentyp deaktiviert",
    no_notify_targets: "Kein Benachrichtigungsziel hinterlegt",
    invalid_notify_target: "Ungültiges Benachrichtigungsziel", notify_failed: "Fehler beim Notify-Aufruf",
    fb_sent: "An Fallback übergeben", fb_partial: "Teilweise an Fallback übergeben",
    fb_already_sent: "Bereits direkt an Fallback übergeben", fb_empty: "Kein anderer Fallback-Empfänger",
    fb_failed: "Fallback-Versand fehlgeschlagen", fb_not_attempted: "Fallback nicht ausgeführt",
    fb_none: "Kein Fallback", untitled: "Ohne Titel",
    fb_blocked: "Kein Fallback-Empfänger war erreichbar", read: "Gelesen",
    due: "Erneut erinnern um", repeat_sent: "Erinnerung übergeben",
    repeat_blocked: "Erinnerung nicht zugestellt", repeat_failed: "Erinnerungsversand fehlgeschlagen",
    repeat_interrupted: "Erinnerungsversand unterbrochen", recipient_changed: "Empfänger oder Gerät nicht mehr zugeordnet",
    invalid_profile: "Empfängerregeln ungültig",
  },
  en: {
    title: "Notifications", refresh: "Refresh", filter: "Status",
    one: "notification", many: "notifications", day_disabled: "Delivery is off for this day",
    outside_day_window: "Outside your delivery window",
    history: "History", availability: "My availability",
    all: "All activity", problems: "Not delivered", forwarded: "Fallback",
    loading: "Loading history …", empty: "No notifications for you yet.",
    noMatch: "No matching notifications.", error: "Could not load notification history.",
    info: "Info", warning: "Warning", critical: "Critical", reminder: "Reminder",
    sent: "Handed off", partial: "Partially handed off", blocked: "Not delivered",
    failed: "Delivery failed", not_attempted: "Dispatch interrupted",
    person_not_home: "Home-only rule: home condition not met",
    weekday_disabled: "Weekday delivery is disabled", weekend_disabled: "Weekend delivery is disabled",
    outside_weekday_window: "Outside weekday hours", outside_weekend_window: "Outside weekend hours",
    dnd_active: "Do not disturb is active", type_not_enabled: "Notification type disabled",
    no_notify_targets: "No notification target configured", invalid_notify_target: "Invalid notification target",
    notify_failed: "Notify action failed", fb_sent: "Handed off to fallback",
    fb_partial: "Partially handed off to fallback", fb_already_sent: "Fallback already notified directly",
    fb_empty: "No other fallback recipient", fb_failed: "Fallback delivery failed",
    fb_not_attempted: "Fallback not attempted", fb_none: "No fallback", untitled: "Untitled",
    fb_blocked: "No fallback recipient was available", read: "Read",
    due: "Remind again at", repeat_sent: "Reminder handed off", repeat_blocked: "Reminder not delivered",
    repeat_failed: "Reminder delivery failed", repeat_interrupted: "Reminder delivery interrupted",
    recipient_changed: "Recipient or device is no longer linked", invalid_profile: "Invalid recipient rules",
  },
};

const icons = { info: "information-outline", warning: "alert-outline", critical: "alert-octagon-outline", reminder: "clock-outline" };
const element = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};

class NotificationDispatcherHistory extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;height:100%;overflow:auto;box-sizing:border-box;--nd-bg:var(--primary-background-color,#f5f7f8);--nd-surface:var(--card-background-color,#fff);--nd-text:var(--primary-text-color,#1d292f);--nd-muted:var(--secondary-text-color,#56676e);--nd-line:var(--divider-color,#d8e1e3);--nd-border:color-mix(in srgb,var(--nd-muted) 45%,var(--nd-surface));--nd-accent:var(--primary-color,#058398);--nd-action:color-mix(in srgb,var(--nd-accent) 57%,#0c4750);--nd-on-action:#fff;--nd-ink:color-mix(in srgb,var(--nd-accent) 55%,var(--nd-text));--nd-tint:color-mix(in srgb,var(--nd-accent) 12%,var(--nd-surface));--nd-mark:color-mix(in srgb,var(--nd-accent) 46%,var(--nd-line));--nd-hover:color-mix(in srgb,var(--nd-text) 6%,var(--nd-surface));--nd-off:color-mix(in srgb,var(--nd-text) 12%,var(--nd-surface));--nd-error:var(--error-color,#bd423e);color:var(--nd-text);background:var(--nd-bg);font:400 15px/1.45 var(--ha-font-family-body,var(--primary-font-family,Roboto,system-ui,sans-serif));letter-spacing:0}
        ${controls}
        header{position:sticky;top:0;z-index:2;background:var(--nd-surface);border-bottom:1px solid var(--nd-line)}.toolbar{display:flex;align-items:center;min-height:58px;padding:5px 18px;gap:10px}
        .brand{width:31px;height:31px;border-radius:7px;display:block}h1{font-size:20px;font-weight:600;line-height:1.2;margin:0;flex:1;overflow-wrap:anywhere}
        .band{background:var(--nd-surface);border-bottom:1px solid var(--nd-line)}.inner,main{width:min(100%,1016px);margin-inline:auto;padding-inline:26px}
        .tabs{display:flex;gap:16px}.tabs button{display:flex;align-items:center;justify-content:center;gap:7px;min-height:47px;padding:4px 5px;border-bottom:3px solid transparent;font-size:14px;font-weight:600;color:var(--nd-muted)}
        .tabs button ha-icon{--mdc-icon-size:18px}.tabs button[aria-selected=true]{color:var(--nd-ink);border-color:var(--nd-ink)}
        main{padding-top:26px;padding-bottom:40px}.feed-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:18px}
        .feed-title{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}h2{font-size:21px;font-weight:600;line-height:1.3;margin:0}
        .count,.type,time,.detail{font-size:13px;color:var(--nd-muted)}.filter{position:relative;display:inline-flex;align-items:center;min-height:38px;color:var(--nd-muted)}
        .filter select{appearance:none;max-width:100%;min-height:38px;padding:5px 30px 5px 34px;color:var(--nd-text);background:var(--nd-surface);border:1px solid var(--nd-border);border-radius:6px;font-size:14px}
        .filter ha-icon{pointer-events:none;position:absolute;left:9px;--mdc-icon-size:17px}.filter ha-icon:last-child{left:auto;right:7px}
        section>h3{font-size:13px;font-weight:600;color:var(--nd-muted);margin:24px 0 1px;padding:0 0 7px;border-bottom:1px solid var(--nd-line)}
        article{--tone:var(--nd-accent);display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:start;gap:12px;padding:16px 2px;border-bottom:1px solid var(--nd-line)}
        article.warning{--tone:var(--warning-color,#af7213)}article.critical{--tone:var(--nd-error)}article.reminder{--tone:var(--success-color,#46856b)}
        .stamp{width:34px;height:34px;display:grid;place-items:center;border-radius:7px;background:color-mix(in srgb,var(--tone) 13%,var(--nd-surface));color:color-mix(in srgb,var(--tone) 70%,var(--nd-text))}
        .type{font-size:12px;font-weight:550}strong{display:block;overflow-wrap:anywhere;font-size:16px;font-weight:600}p{overflow-wrap:anywhere;white-space:pre-wrap;margin:3px 0 7px}
        time{font-variant-numeric:tabular-nums;white-space:nowrap}.route{display:flex;align-items:baseline;gap:6px;font-size:13px;font-weight:550;overflow-wrap:anywhere;margin-top:6px}
        .route::before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;flex:none;background:var(--nd-muted)}.route.sent::before{background:var(--success-color,#439476)}.route.failed::before{background:var(--nd-error)}.route.partial::before,.route.blocked::before{background:var(--warning-color,#be851a)}
        .detail{padding-left:13px;overflow-wrap:anywhere}.empty{display:flex;align-items:center;gap:10px;padding:26px 0;color:var(--nd-muted);border-top:1px solid var(--nd-line)}
        @media(max-width:600px){.inner,main{padding-inline:16px}.toolbar{padding-inline:8px;gap:7px}main{padding-top:18px}.tabs{gap:10px}.tabs button{padding-inline:2px}.feed-head{margin-bottom:10px;gap:8px}article{grid-template-columns:30px minmax(0,1fr) auto;gap:7px}.stamp{width:28px;height:28px}.feed-title{gap:5px}.count{font-size:12px}}
      </style>
      <header><div class="toolbar"><ha-menu-button></ha-menu-button><img class="brand" width="31" height="31" alt="" src="${new URL("./icon.png", import.meta.url).href}"><h1></h1>
        <button class="icon-btn" id="refresh" type="button">${glyph("refresh")}</button></div></header>
      <div class="band"><div class="inner tabs" role="tablist"><button type="button" id="tab-history" role="tab" aria-controls="history">${glyph("history")}<span></span></button>
        <button type="button" id="tab-availability" role="tab" aria-controls="availability">${glyph("calendar-clock-outline")}<span></span></button></div></div>
      <main>
        <div id="history" role="tabpanel" aria-labelledby="tab-history"><div class="feed-head"><div class="feed-title"><h2></h2><span class="count"></span></div>
          <label class="filter">${glyph("filter-variant")}<select></select>${glyph("chevron-down")}</label></div><section aria-live="polite"></section></div>
        <notification-dispatcher-availability id="availability" role="tabpanel" aria-labelledby="tab-availability" hidden></notification-dispatcher-availability>
      </main>`;
    this.$ = (selector) => this.shadowRoot.querySelector(selector);
    this.view = "history";
    this.$("#refresh").onclick = () => this.load();
    for (const tab of ["history", "availability"]) {
      this.$("#tab-" + tab).onclick = () => this.selectView(tab);
      this.$("#tab-" + tab).onkeydown = e => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
        e.preventDefault();
        const next = e.key === "Home" ? "history" : e.key === "End" ? "availability" : tab === "history" ? "availability" : "history";
        this.selectView(next);
        this.$("#tab-" + next).focus();
      };
    }
    this.$("select").onchange = () => this.render();
    this.onVisible = () => { if (!document.hidden) this.load(); };
    this.epoch = 0;
    this.rows = [];
    this.phase = "loading";
  }

  connectedCallback() {
    document.addEventListener("visibilitychange", this.onVisible);
    this.timer = window.setInterval(this.onVisible, 30000);
    this.render();
    this.load();
  }
  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this.onVisible);
    clearInterval(this.timer);
    this.reset();
  }
  reset() {
    ++this.epoch;
    this.rows = [];
    this.phase = "loading";
    this.busy = false;
    this.render();
  }
  selectView(view) {
    this.view = view;
    this.render();
    if (view === "history") this.load();
  }
  set narrow(value) { this.$("ha-menu-button").narrow = value; }
  set hass(value) {
    const old = this._hass;
    const changed = old?.user?.id !== value?.user?.id || old?.connection !== value?.connection;
    this._hass = value;
    this.$("ha-menu-button").hass = value;
    if (changed) {
      this.view = "history";
      this.$("#availability").active = false;
    }
    this.$("#availability").hass = value;
    if (changed) {
      this.reset();
      this.load();
    } else if (old?.language !== value?.language || old?.config?.time_zone !== value?.config?.time_zone) {
      this.render();
    }
  }
  async load() {
    if (this.view !== "history" || !this.isConnected || !this._hass?.user?.id || this.busy) return;
    const epoch = this.epoch;
    this.busy = true;
    try {
      const rows = await this._hass.callWS({ type: "notification_dispatcher/history" });
      if (this.epoch !== epoch) return;
      this.rows = rows;
      this.phase = "ready";
    } catch {
      if (this.epoch !== epoch) return;
      this.rows = [];
      this.phase = "error";
    } finally {
      if (this.epoch === epoch) {
        this.busy = false;
        this.render();
      }
    }
  }
  render() {
    const locale = this._hass?.language || "de";
    const w = locale.startsWith("de") ? words.de : words.en;
    const zone = this._hass?.config?.time_zone;
    const day = new Intl.DateTimeFormat(locale, { dateStyle: "long", timeZone: zone });
    const clock = new Intl.DateTimeFormat(locale, { timeStyle: "short", timeZone: zone });
    this.$("h1").textContent = w.title;
    const refresh = this.$("#refresh");
    refresh.title = w.refresh;
    refresh.setAttribute("aria-label", w.refresh);
    refresh.hidden = this.view !== "history";
    this.$(".tabs").setAttribute("aria-label", w.title);
    for (const name of ["history", "availability"]) {
      const tab = this.$("#tab-" + name);
      tab.querySelector("span").textContent = w[name];
      tab.tabIndex = this.view === name ? 0 : -1;
      tab.setAttribute("aria-selected", String(this.view === name));
    }
    this.$("#history").hidden = this.view !== "history";
    this.$("#availability").active = this.view === "availability";
    this.$(".feed-title h2").textContent = w.history;
    this.$(".count").textContent = this.phase === "ready" ? this.rows.length + " " + w[this.rows.length === 1 ? "one" : "many"] : "";
    const select = this.$("select");
    select.setAttribute("aria-label", w.filter);
    const filter = select.value || "all";
    if (this.filterLanguage !== locale) {
      select.replaceChildren(...["all", "problems", "forwarded"].map(key => new Option(w[key], key)));
      select.value = filter;
      this.filterLanguage = locale;
    }
    const list = this.$("section");
    list.replaceChildren();
    let currentDay;
    for (const row of this.rows) {
      const routes = row.routes.filter(r => filter === "all" ||
        (filter === "problems" ? r.status !== "sent" || ["blocked", "failed", "interrupted"].includes(r.repeat) : r.fallback || r.for.length));
      if (!routes.length) continue;
      const date = new Date(row.timestamp);
      const group = day.format(date);
      if (currentDay !== group) list.append(element("h3", group));
      currentDay = group;
      const article = element("article", null, row.type);
      const icon = element("ha-icon");
      icon.setAttribute("icon", "mdi:" + (icons[row.type] || icons.info));
      icon.setAttribute("aria-hidden", "true");
      const body = element("div");
      body.append(element("span", w[row.type], "type"), element("strong", row.title || w.untitled), element("p", row.message));
      for (const route of routes) {
        const prefix = route.for.length ? "FB: " + route.for.map(name => "@" + name.replace(/\s+/g, "_")).join(" ") + " · " : "";
        body.append(element("div", prefix + w[route.status], "route " + route.status));
        const reason = route.reason && route.reason !== "not_attempted" ? w[route.reason] : "";
        const fb = route.fallback ? w["fb_" + route.fallback] : !route.for.length && route.status !== "sent" ? w.fb_none : "";
        if (reason) body.append(element("div", reason, "detail"));
        if (fb) body.append(element("div", fb, "detail"));
        if (route.read) body.append(element("div", w.read, "detail"));
        if (route.due) body.append(element("div", w.due + " " + clock.format(new Date(route.due)), "detail"));
        if (route.repeat) {
          const parts = [w["repeat_" + route.repeat], w[route.repeat_reason]].filter(Boolean);
          body.append(element("div", parts.join(" · "), "detail"));
        }
      }
      const time = element("time", clock.format(date));
      time.dateTime = row.timestamp;
      const stamp = element("div", null, "stamp");
      stamp.append(icon);
      article.append(stamp, body, time);
      list.append(article);
    }
    if (!list.childElementCount) {
      const state = this.phase === "ready" ? (this.rows.length ? "noMatch" : "empty") : this.phase;
      const empty = element("div", null, "empty");
      empty.innerHTML = glyph("email-outline"); empty.append(element("span", w[state])); list.append(empty);
    }
  }
}
if (!customElements.get("notification-dispatcher-history")) {
  customElements.define("notification-dispatcher-history", NotificationDispatcherHistory);
}
