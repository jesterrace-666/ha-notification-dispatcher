const words = {
  de: {
    title: "Notification Verlauf", refresh: "Aktualisieren", filter: "Status",
    all: "Alle Vorgänge", problems: "Nicht zugestellt", forwarded: "Fallback",
    loading: "Verlauf wird geladen …", empty: "Noch keine Nachrichten für dich.",
    noMatch: "Keine passenden Nachrichten.", error: "Verlauf konnte nicht geladen werden.",
    info: "Info", warning: "Warnung", critical: "Kritisch", reminder: "Erinnerung",
    sent: "Übergeben", partial: "Teilweise übergeben", blocked: "Nicht zugestellt",
    failed: "Versand fehlgeschlagen", not_attempted: "Versand abgebrochen",
    person_not_home: "Nur wenn zuhause: Zuhause-Bedingung nicht erfüllt",
    weekday_disabled: "Werktags ist keine Zustellung aktiviert",
    weekend_disabled: "Am Wochenende ist keine Zustellung aktiviert",
    outside_weekday_window: "Außerhalb des Werktag-Zeitfensters",
    outside_weekend_window: "Außerhalb des Wochenend-Zeitfensters",
    dnd_active: "Nicht stören: Ruhezeit aktiv", type_not_enabled: "Nachrichtentyp deaktiviert",
    no_notify_targets: "Kein Benachrichtigungsziel hinterlegt",
    invalid_notify_target: "Ungültiges Benachrichtigungsziel", notify_failed: "Fehler beim Notify-Aufruf",
    fb_sent: "An Fallback übergeben", fb_partial: "Teilweise an Fallback übergeben",
    fb_already_sent: "Fallback bereits direkt erreicht", fb_empty: "Kein anderer Fallback-Empfänger",
    fb_failed: "Fallback-Versand fehlgeschlagen", fb_not_attempted: "Fallback nicht ausgeführt",
    fb_none: "Kein Fallback", untitled: "Ohne Titel",
  },
  en: {
    title: "Notification history", refresh: "Refresh", filter: "Status",
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
        :host{display:block;height:100%;overflow:auto;box-sizing:border-box;background:var(--primary-background-color,#fafafa);color:var(--primary-text-color,#202124);font:inherit}
        *,*::before,*::after{box-sizing:border-box} header{position:sticky;top:0;z-index:1;display:flex;align-items:center;gap:12px;min-height:56px;padding:4px 16px;background:var(--app-header-background-color,var(--card-background-color,white));color:var(--app-header-text-color,var(--primary-text-color));border-bottom:1px solid var(--divider-color,#ddd)}
        h1{font-size:20px;line-height:1.3;font-weight:500;margin:0;flex:1;overflow-wrap:anywhere} button{background:transparent;color:inherit;border:0;width:44px;height:44px;cursor:pointer}
        main{max-width:820px;margin:auto;padding:20px clamp(12px,3%,28px) 40px} nav{display:flex;justify-content:flex-end} select{font:inherit;font-size:14px;max-width:100%;padding:7px;color:inherit;background:var(--card-background-color,white);border:1px solid var(--divider-color,#ccc);border-radius:4px}
        h2{font-size:14px;font-weight:500;color:var(--secondary-text-color,#62676c);margin:20px 0 2px} article{display:grid;grid-template-columns:28px minmax(0,1fr) auto;align-items:start;gap:8px 12px;padding:15px 0;border-bottom:1px solid var(--divider-color,#ddd)}
        article ha-icon{margin-top:2px;color:var(--info-color,#297da0)} article.warning ha-icon{color:var(--warning-color,#b26813)} article.critical ha-icon{color:var(--error-color,#b93441)} article.reminder ha-icon{color:var(--secondary-text-color,#68626f)}
        strong{display:block;overflow-wrap:anywhere;font-weight:600} p{overflow-wrap:anywhere;white-space:pre-wrap;margin:5px 0;line-height:1.45} time,.type,.detail{color:var(--secondary-text-color,#60656a);font-size:13px}
        .route{margin-top:7px;font-size:14px;overflow-wrap:anywhere} time{white-space:nowrap} .empty{padding:24px 0;color:var(--secondary-text-color,#60656a)}
        @media(max-width:440px){main{padding:12px}article{column-gap:7px}header{gap:6px;padding-inline:6px}}
      </style>
      <header><ha-menu-button></ha-menu-button><h1></h1><button type="button"><ha-icon icon="mdi:refresh"></ha-icon></button></header>
      <main><nav><select></select></nav><section aria-live="polite"></section></main>`;
    this.$ = (selector) => this.shadowRoot.querySelector(selector);
    this.$("button").onclick = () => this.load();
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
  set narrow(value) { this.$("ha-menu-button").narrow = value; }
  set hass(value) {
    const old = this._hass;
    const changed = old?.user?.id !== value?.user?.id || old?.connection !== value?.connection;
    this._hass = value;
    this.$("ha-menu-button").hass = value;
    if (changed) {
      this.reset();
      this.load();
    } else if (old?.language !== value?.language || old?.config?.time_zone !== value?.config?.time_zone) {
      this.render();
    }
  }
  async load() {
    if (!this.isConnected || !this._hass?.user?.id || this.busy) return;
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
    const refresh = this.$("button");
    refresh.title = w.refresh;
    refresh.setAttribute("aria-label", w.refresh);
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
        (filter === "problems" ? r.status !== "sent" : r.fallback || r.for.length));
      if (!routes.length) continue;
      const date = new Date(row.timestamp);
      const group = day.format(date);
      if (currentDay !== group) list.append(element("h2", group));
      currentDay = group;
      const article = element("article", null, row.type);
      const icon = element("ha-icon");
      icon.setAttribute("icon", "mdi:" + (icons[row.type] || icons.info));
      icon.setAttribute("aria-hidden", "true");
      const body = element("div");
      body.append(element("span", w[row.type], "type"), element("strong", row.title || w.untitled), element("p", row.message));
      for (const route of routes) {
        const prefix = route.for.length ? "FB: " + route.for.map(name => "@" + name.replace(/\s+/g, "_")).join(" ") + " · " : "";
        body.append(element("div", prefix + w[route.status], "route"));
        const reason = route.reason && route.reason !== "not_attempted" ? w[route.reason] : "";
        const fb = route.fallback ? w["fb_" + route.fallback] : route.status === "blocked" ? w.fb_none : "";
        if (reason || fb) body.append(element("div", [reason, fb].filter(Boolean).join(" · "), "detail"));
      }
      const time = element("time", clock.format(date));
      time.dateTime = row.timestamp;
      article.append(icon, body, time);
      list.append(article);
    }
    if (!list.childElementCount) {
      const state = this.phase === "ready" ? (this.rows.length ? "noMatch" : "empty") : this.phase;
      list.append(element("p", w[state], "empty"));
    }
  }
}
if (!customElements.get("notification-dispatcher-history")) {
  customElements.define("notification-dispatcher-history", NotificationDispatcherHistory);
}
