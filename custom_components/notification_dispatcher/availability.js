// Personal settings are fetched for the active HA session, never from browser storage.
const strings = {
  de: {
    hours: "Zustellzeiten", always: "Rund um die Uhr (24/7)", scheduled: "Zeitfenster",
    weekday: "Werktage", weekend: "Wochenende", start: "Von", end: "Bis",
    presence: "Anwesenheit", home: "Nur wenn zuhause", types: "Nachrichtentypen",
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
    hours: "Delivery hours", always: "Around the clock (24/7)", scheduled: "Time windows",
    weekday: "Weekdays", weekend: "Weekends", start: "From", end: "Until",
    presence: "Presence", home: "Only when home", types: "Notification types",
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
const days = { weekday: "08:00-22:00", weekend: "09:00-22:00" };
const types = ["info", "warning", "reminder"];
const command = "notification_dispatcher/preferences";

function dayRow(day) {
  const clock = part => `<label><span id="${day}-${part}-label" data-i="${part}"></span>
    <input id="${day}-${part}" type="time" step="60" required aria-labelledby="${day}-label ${day}-${part}-label"></label>`;
  return `<div class="day"><label class="check"><input id="${day}" type="checkbox">
    <span id="${day}-label" data-i="${day}"></span></label>
    <div class="clocks" id="${day}-times">${clock("start")}${clock("end")}</div></div>`;
}

class DispatcherAvailability extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host{display:block;max-width:650px;color:var(--primary-text-color,#202124)}:host([hidden]),[hidden]{display:none!important}
        *,*::before,*::after{box-sizing:border-box} form,fieldset{margin:0;padding:0;border:0;min-width:0}
        .group{padding:4px 0 17px;margin:0 0 18px;border-bottom:1px solid var(--divider-color,#ddd)}
        legend{font-size:16px;font-weight:600;margin:0 0 7px;padding:0}
        .choices,.clocks,.actions{display:flex;align-items:center;gap:6px 20px;flex-wrap:wrap}
        .check{display:inline-flex;align-items:center;gap:8px;min-height:40px;cursor:pointer}
        input{accent-color:var(--primary-color,#03a9f4);font:inherit}
        input[type=checkbox],input[type=radio]{width:18px;height:18px;margin:0;flex:none}
        .day{display:grid;grid-template-columns:minmax(8rem,1fr) minmax(0,2fr);align-items:center;gap:4px 14px;padding:9px 0}
        .clocks{gap:12px}.clocks label{display:grid;gap:4px;color:var(--secondary-text-color,#60656a);font-size:13px}
        input[type=time]{min-width:0;max-width:100%;height:38px;padding:3px 7px;background:var(--card-background-color,white);color:var(--primary-text-color,#202124);border:1px solid var(--divider-color,#aaa);border-radius:4px;font-size:15px}
        .note,#feedback{color:var(--secondary-text-color,#60656a);font-size:14px;line-height:1.5;margin:8px 0}
        #feedback.error{color:var(--error-color,#b3261e)}button{min-height:40px;padding:5px 14px;font:inherit;font-weight:500;cursor:pointer;border:0;border-radius:4px;background:transparent;color:var(--primary-text-color,#202124)}
        button[type=submit]{background:var(--primary-color,#0279a9);color:var(--text-primary-color,white)}
        button:disabled{opacity:.45;cursor:default} :focus-visible{outline:2px solid var(--primary-color,#0288d1);outline-offset:2px}
        @media(max-width:460px){.day{grid-template-columns:1fr}.clocks{padding-left:26px}.choices{column-gap:14px}}
      </style>
      <form hidden>
        <fieldset id="editable">
          <fieldset class="group"><legend data-i="hours"></legend>
            <div class="choices">
              <label class="check"><input type="radio" name="mode" id="always"><span data-i="always"></span></label>
              <label class="check"><input type="radio" name="mode" id="scheduled"><span data-i="scheduled"></span></label>
            </div>
            <div id="schedule">${Object.keys(days).map(dayRow).join("")}</div>
            <div id="quiet" hidden><p class="note" id="quiet-label"></p>
              <label class="check"><input type="checkbox" id="clear-quiet"><span data-i="clearQuiet"></span></label></div>
          </fieldset>
          <fieldset class="group"><legend data-i="presence"></legend>
            <label class="check"><input id="home" type="checkbox"><span data-i="home"></span></label>
          </fieldset>
          <fieldset class="group"><legend data-i="types"></legend>
            <div class="choices">${types.map(t => `<label class="check"><input id="${t}" type="checkbox"><span data-i="${t}"></span></label>`).join("")}</div>
            <p class="note" data-i="critical"></p>
          </fieldset>
        </fieldset>
        <div class="actions"><button type="submit"></button><button type="button" id="discard" data-i="discard"></button></div>
      </form>
      <p id="feedback" role="status" aria-live="polite"></p><button type="button" id="reload" hidden data-i="reload"></button>`;
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
    } else if (old?.language !== value?.language) this.paint();
  }
  set active(value) {
    const opening = value && !this._active;
    this._active = value;
    this.hidden = !value;
    if (opening && !this.dirty && !this.saving && !this.conflict) this.load();
  }
  get active() { return this._active; }
  reset() {
    ++this.epoch;
    this.base = null;
    this.busy = this.saving = this.conflict = false;
    this.notice = "";
    this.$("form").reset();
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
    for (const [day, def] of Object.entries(days)) {
      const win = s[day + "_window"];
      this.$("#" + day).checked = !!win;
      const [start, end] = (win || def).split("-");
      this.$("#" + day + "-start").value = start;
      this.$("#" + day + "-end").value = end;
    }
    this.paint();
  }
  values() {
    const always = this.$("#always").checked;
    const result = { always_notify: always, only_when_home: this.$("#home").checked,
      enabled_types: types.filter(t => this.$("#" + t).checked).sort() };
    for (const day of Object.keys(days)) {
      const key = day + "_window";
      result[key] = always ? this.base.settings[key] : this.$("#" + day).checked
        ? this.$("#" + day + "-start").value + "-" + this.$("#" + day + "-end").value : "";
    }
    return result;
  }
  get dirty() {
    return !!this.base && (this.clearQuiet || Object.entries(this.values()).some(([k, v]) =>
      JSON.stringify(v) !== JSON.stringify(this.base.settings[k])));
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
    for (const day of Object.keys(days)) {
      const off = always || !this.$("#" + day).checked;
      this.$("#" + day + "-times").hidden = off;
      for (const part of ["start", "end"]) this.$("#" + day + "-" + part).disabled = off;
    }
    const quiet = this.base?.quiet_window;
    this.$("#quiet").hidden = !quiet || (always && !this.base.quiet_in_24h);
    this.$("#quiet-label").textContent = quiet ? w.quiet + ": " + quiet : "";
    this.$("button[type=submit]").textContent = this.saving ? w.saving : w.save;
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
