import { controls, glyph } from "./panel-ui.js";
import { dayKeys, profileWeek, sameWeek } from "./week-picker.js";

// Personal settings are fetched for the active HA session, never from browser storage.
const strings = {
  de: {
    hours: "Zustellzeiten", always: "Rund um die Uhr", scheduled: "Wochenplan",
    full: "24 Stunden · 7 Tage", delivery: "Zustellung", locked: "Immer aktiv", criticalType: "Kritisch",
    home: "Nur wenn zuhause", types: "Nachrichtentypen", pending: "Ungespeicherte Änderungen",
    info: "Info", warning: "Warnung", reminder: "Erinnerung",
    critical: "Kritische Meldungen werden immer zugestellt.", quiet: "Gespeicherte Ruhezeit", clearQuiet: "Diese Ruhezeit aufheben",
    save: "Speichern", saving: "Wird gespeichert …", discard: "Verwerfen", reload: "Neu laden",
    loading: "Erreichbarkeit wird geladen …", saved: "Erreichbarkeit gespeichert.",
    unlinked: "Deinem HA-Konto ist keine Dispatcher-Person zugeordnet. Ein Administrator kann die Zuordnung einrichten.",
    ambiguous: "Dein HA-Konto ist mehreren Dispatcher-Profilen zugeordnet. Bitte einen Administrator, die Zuordnung zu prüfen.",
    loadError: "Erreichbarkeit konnte nicht geladen werden.", saveError: "Speichern fehlgeschlagen. Deine Änderungen sind noch im Formular.",
    conflict: "Deine Einstellungen wurden inzwischen geändert. Lade den aktuellen Stand neu.",
    invalid: "Bitte prüfe die Zeitfenster.", invalidProfile: "Ein gespeichertes Zeitfenster ist ungültig. Bitte einen Administrator, es zu prüfen.",
  },
  en: {
    hours: "Delivery hours", always: "Around the clock", scheduled: "Week plan",
    full: "24 hours · 7 days", delivery: "Delivery", locked: "Always on", criticalType: "Critical",
    home: "Only when home", types: "Notification types", pending: "Unsaved changes",
    info: "Info", warning: "Warning", reminder: "Reminder",
    critical: "Critical notifications are always delivered.", quiet: "Saved quiet hours", clearQuiet: "Remove these quiet hours",
    save: "Save", saving: "Saving …", discard: "Discard", reload: "Reload",
    loading: "Loading availability …", saved: "Availability saved.",
    unlinked: "Your HA account is not linked to a dispatcher person. An administrator can set this up.",
    ambiguous: "Your HA account is linked to multiple dispatcher profiles. Ask an administrator to check the mapping.",
    loadError: "Could not load availability.", saveError: "Could not save. Your changes are still in the form.",
    conflict: "Your settings have changed elsewhere. Reload the current settings.",
    invalid: "Check the time windows.", invalidProfile: "A saved time window is invalid. Ask an administrator to check it.",
  },
};
const types = ["info", "warning", "reminder"];
const typeIcons = {info:"information-outline", warning:"alert-outline", reminder:"clock-outline"};
const command = "notification_dispatcher/preferences";

class DispatcherAvailability extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;color:var(--nd-text)}:host([hidden]){display:none}${controls}
        form,fieldset{margin:0;padding:0;border:0;min-width:0}.columns{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(245px,1fr);gap:32px}
        .delivery{border-left:1px solid var(--nd-line);padding-left:28px}h2{font-size:20px;font-weight:600;margin:0}h3{font-size:14px;font-weight:600;margin:18px 0 6px}
        .top,.row,.save-bar,.actions,.quiet{display:flex;align-items:center;gap:9px}.top{justify-content:space-between;flex-wrap:wrap;min-height:34px;margin-bottom:15px}
        .zone{color:var(--nd-muted);font-size:12px;display:inline-flex;align-items:center;gap:4px}.zone ha-icon{--mdc-icon-size:15px}
        .mode{display:inline-grid;grid-template-columns:1fr 1fr;gap:3px;padding:3px;border:1px solid var(--nd-line);border-radius:7px;background:var(--nd-hover);margin-bottom:22px;max-width:100%}
        .mode label{position:relative;min-width:0;cursor:pointer}.mode input{position:absolute;opacity:0}
        .mode span{min-height:38px;display:flex;align-items:center;justify-content:center;gap:7px;padding:5px 12px;border:1px solid transparent;border-radius:4px;color:var(--nd-muted);font-size:14px;font-weight:550;text-align:center}
        .mode input:checked+span{color:var(--nd-ink);border-color:var(--nd-line);background:var(--nd-surface);box-shadow:0 1px 2px #0001}
        .mode b{font-weight:inherit}.mode input:focus-visible+span{outline:2px solid var(--nd-ink)}.mode ha-icon{--mdc-icon-size:18px}
        .row{min-height:46px;cursor:pointer;border-bottom:1px solid var(--nd-line);font-size:15px}.row .switch,.lock{margin-left:auto}.row.critical{cursor:default;border:0}
        .marker{display:grid;place-items:center;flex:none;width:29px;height:29px;border-radius:6px;color:var(--nd-ink);background:var(--nd-tint)}
        .marker ha-icon{--mdc-icon-size:17px}.warning{--tone:var(--warning-color,#bd7a13)}.reminder{--tone:var(--success-color,#3b8669)}.critical{--tone:var(--error-color,#cc5355)}
        .warning .marker,.reminder .marker,.critical .marker{color:color-mix(in srgb,var(--tone) 70%,var(--nd-text));background:color-mix(in srgb,var(--tone) 13%,var(--nd-surface))}
        .lock{display:flex;align-items:center;gap:4px;color:var(--nd-muted);font-size:12px}.lock ha-icon{--mdc-icon-size:14px}
        .full{display:flex;align-items:center;gap:12px;border-block:1px solid var(--nd-line);padding:18px 2px;font-weight:550}
        .full>ha-icon{--mdc-icon-size:26px;color:var(--nd-ink)}.quiet{align-items:flex-start;flex-wrap:wrap;justify-content:space-between;margin-top:16px;font-size:13px;color:var(--nd-muted)}
        .quiet p{margin:0}.quiet label{display:flex;align-items:center;gap:5px;cursor:pointer}.quiet input{accent-color:var(--nd-action)}
        .save-bar{justify-content:space-between;border-top:1px solid var(--nd-line);margin-top:24px;padding-top:14px;flex-wrap:wrap}
        #dirty,#feedback{font-size:13px;color:var(--nd-muted)}#dirty:not(:empty)::before{content:"";display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--warning-color,#bd7a13);margin-right:6px}
        .actions{margin-left:auto}#feedback:empty{margin:0}#feedback.error{color:var(--nd-error)}
        @media(max-width:720px){.columns{grid-template-columns:1fr;gap:22px}.delivery{border-left:0;padding-left:0;border-top:1px solid var(--nd-line);padding-top:16px}.delivery .top{margin-bottom:6px}}
        @media(max-width:380px){.mode span{padding:4px 7px;gap:4px}.save-bar{gap:8px}.mode{width:100%}.zone{font-size:11px}}
      </style>
      <form hidden>
        <fieldset id="editable"><div class="columns">
          <section aria-labelledby="hours-title"><div class="top"><h2 id="hours-title" data-i="hours"></h2><span class="zone">${glyph("earth")}<span id="zone"></span></span></div>
            <div class="mode" role="radiogroup" aria-labelledby="hours-title">
              <label><input type="radio" name="mode" id="scheduled"><span>${glyph("calendar-week-outline")}<b data-i="scheduled"></b></span></label>
              <label><input type="radio" name="mode" id="always"><span>${glyph("infinity")}<b>24/7</b></span></label></div>
            <dispatcher-week-picker id="schedule"></dispatcher-week-picker>
            <div class="full" id="full" hidden>${glyph("clock-check-outline")}<span data-i="full"></span></div>
            <div class="quiet" id="quiet" hidden><p id="quiet-label"></p><label><input type="checkbox" id="clear-quiet"><span data-i="clearQuiet"></span></label></div>
          </section>
          <section class="delivery" aria-labelledby="delivery-title"><div class="top"><h2 id="delivery-title" data-i="delivery"></h2></div>
            <label class="row"><span class="marker">${glyph("home-outline")}</span><span data-i="home"></span><input class="switch" id="home" type="checkbox" role="switch"></label>
            <h3 data-i="types"></h3>
            ${types.map(t => `<label class="row ${t}"><span class="marker">${glyph(typeIcons[t])}</span><span data-i="${t}"></span><input class="switch" id="${t}" type="checkbox" role="switch"></label>`).join("")}
            <div class="row critical"><span class="marker">${glyph("alert-octagon-outline")}</span><span data-i="criticalType"></span><span class="lock">${glyph("lock-outline")}<span data-i="locked"></span></span></div>
          </section>
        </div></fieldset>
        <div class="save-bar"><span id="dirty"></span><div class="actions"><button type="button" class="quiet-btn" id="discard" data-i="discard"></button>
          <button type="submit" class="solid-btn">${glyph("check")}<span></span></button></div></div>
      </form>
      <p id="feedback" role="status" aria-live="polite"></p><button type="button" class="quiet-btn" id="reload" hidden data-i="reload"></button>`;
    this.$ = s => this.shadowRoot.querySelector(s);
    this.epoch = 0;
    this.$("form").oninput = () => {
      if (!this.conflict) this.notice = "";
      this.paint();
    };
    this.$("form").onsubmit = e => { e.preventDefault(); this.save(); };
    this.$("#discard").onclick = () => this.fill(this.base);
    this.$("#reload").onclick = () => this.load();
    this.reset();
  }

  connectedCallback() { if (this.active && !this.base) this.load(); }
  disconnectedCallback() { this.reset(); }
  set hass(value) {
    const old = this._hass;
    this._hass = value;
    if (old?.user?.id !== value?.user?.id || old?.connection !== value?.connection) {
      this.reset();
      if (this.active) this.load();
    } else if (old?.language !== value?.language || old?.config?.time_zone !== value?.config?.time_zone) this.paint();
  }
  set active(value) {
    const opening = value && !this._active;
    this._active = value;
    this.hidden = !value;
    if (!value) this.$("#schedule").close();
    if (opening && !this.dirty && !this.saving && !this.conflict) this.load();
  }
  get active() { return this._active; }
  reset() {
    ++this.epoch;
    this.base = null;
    this.busy = this.saving = this.conflict = false;
    this.notice = "";
    this.$("form").reset();
    this.$("#schedule").value = {};
    this.paint();
  }
  async load() {
    if (!this.isConnected || !this._hass?.user?.id || this.busy || this.saving) return;
    this.reset();
    const epoch = this.epoch;
    this.busy = true;
    this.notice = "loading";
    this.paint();
    try {
      const result = await this._hass.callWS({ type: command });
      if (this.epoch !== epoch) return;
      if (result.state === "ready") this.fill(result);
      else this.notice = result.state === "ambiguous" ? "ambiguous" : "unlinked";
    } catch (e) {
      if (this.epoch === epoch) this.notice = e?.code === "invalid_profile" ? "invalidProfile" : "loadError";
    } finally {
      if (this.epoch === epoch) { this.busy = false; this.paint(); }
    }
  }
  fill(result, notice = "") {
    this.base = result;
    this.notice = notice;
    const s = result.settings;
    this.$(s.always_notify ? "#always" : "#scheduled").checked = true;
    this.$("#home").checked = s.only_when_home;
    this.$("#clear-quiet").checked = false;
    for (const t of types) this.$("#" + t).checked = s.enabled_types.includes(t);
    this.$("#schedule").value = profileWeek(s);
    this.paint();
  }
  values() {
    const always = this.$("#always").checked;
    const result = { always_notify: always, only_when_home: this.$("#home").checked,
      enabled_types: types.filter(t => this.$("#" + t).checked).sort() };
    const base = this.base.settings, before = profileWeek(base);
    const week = always ? before : this.$("#schedule").value;
    result.weekday_window = base.weekday_window;
    result.weekend_window = base.weekend_window;
    if (base.day_windows !== undefined || !sameWeek(week, before)) {
      result.day_windows = week;
      if (!sameWeek(week, before)) for (const [key, keys] of [
        ["weekday_window",dayKeys.slice(0,5)], ["weekend_window",dayKeys.slice(5)]]) {
        const unique = new Set(keys.map(k=>week[k] || ""));
        if (unique.size === 1) result[key] = [...unique][0];
      }
    }
    return result;
  }
  get dirty() {
    return !!this.base && (this.clearQuiet || Object.entries(this.values()).some(([k, v]) =>
      k === "day_windows" ? !sameWeek(v, profileWeek(this.base.settings)) : JSON.stringify(v) !== JSON.stringify(this.base.settings[k])));
  }
  get clearQuiet() { return !this.$("#quiet").hidden && this.$("#clear-quiet").checked; }
  async save() {
    if (!this.dirty || this.saving || this.conflict || !this.$("form").reportValidity()) return;
    const epoch = this.epoch;
    const settings = this.values();
    this.saving = true;
    this.notice = "";
    this.paint();
    try {
      const result = await this._hass.callWS({ type: command + "/update", revision: this.base.revision,
        settings, ...(this.clearQuiet ? { clear_quiet_hours: true } : {}) });
      if (this.epoch === epoch) this.fill(result, "saved");
    } catch (e) {
      if (this.epoch !== epoch) return;
      if (e?.code === "profile_unavailable") { this.reset(); this.load(); return; }
      this.conflict = e?.code === "preferences_changed";
      this.notice = this.conflict ? "conflict" : e?.code === "invalid_preferences" ? "invalid" : "saveError";
    } finally {
      if (this.epoch === epoch) { this.saving = false; this.paint(); }
    }
  }
  paint() {
    const w = (this._hass?.language || "de").startsWith("de") ? strings.de : strings.en;
    for (const node of this.shadowRoot.querySelectorAll("[data-i]")) node.textContent = w[node.dataset.i];
    this.$("form").hidden = !this.base;
    this.$("#editable").disabled = this.saving || this.conflict;
    const always = this.$("#always").checked;
    this.$("#schedule").hidden = always;
    this.$("#schedule").disabled = this.saving || this.conflict || always;
    this.$("#schedule").language = this._hass?.language;
    this.$("#full").hidden = !always;
    this.$("#always").setAttribute("aria-label", w.always + " (24/7)");
    this.$("#always").parentElement.title = w.always;
    this.$("#zone").textContent = this._hass?.config?.time_zone || "";
    this.$(".zone").hidden = !this._hass?.config?.time_zone;
    const quiet = this.base?.quiet_window;
    this.$("#quiet").hidden = !quiet || (always && !this.base.quiet_in_24h);
    this.$("#quiet-label").textContent = quiet ? w.quiet + ": " + quiet : "";
    this.$("button[type=submit] span").textContent = this.saving ? w.saving : w.save;
    this.$("#dirty").textContent = this.dirty ? w.pending : "";
    this.$("button[type=submit]").disabled = !this.dirty || this.saving || this.conflict;
    this.$("#discard").hidden = !this.dirty || this.conflict;
    this.$("#discard").disabled = this.saving;
    this.$("#feedback").textContent = w[this.notice] || "";
    this.$("#feedback").classList.toggle("error", ["loadError", "saveError", "invalid", "conflict", "invalidProfile"].includes(this.notice));
    this.$("#reload").hidden = !["unlinked", "ambiguous", "loadError", "invalidProfile", "conflict"].includes(this.notice);
  }
}
if (!customElements.get("notification-dispatcher-availability")) {
  customElements.define("notification-dispatcher-availability", DispatcherAvailability);
}
