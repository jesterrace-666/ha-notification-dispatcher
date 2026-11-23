import { controls, glyph } from "./panel-ui.js";

export const dayKeys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
export function profileWeek(settings) {
  if (settings.day_windows !== undefined) return { ...settings.day_windows };
  return Object.fromEntries(dayKeys.flatMap((key, i) => {
    const win = settings[i < 5 ? "weekday_window" : "weekend_window"];
    return win ? [[key, win]] : [];
  }));
}
export const sameWeek = (a, b) => dayKeys.every(k => a[k] === b[k]);
const words = {
  de: {
    short: ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
    long: ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    week: "Wochenplan", hours: "Zeitfenster", add: "Zeitfenster hinzufügen", edit: "Zeitfenster bearbeiten",
    weekdays: "Mo – Fr", weekend: "Sa – So", every: "Alle Tage", individual: "Eigene Auswahl",
    preset: "Tagesauswahl", days: "Wochentage", none: "Kein Zeitfenster", empty: "Keine Zustelltage ausgewählt.",
    allDay: "Ganztägig", from: "Von", to: "Bis", hour: "Stunde", minute: "Minute",
    overnight: "Endet am Folgetag.", equal: "Gleiche Uhrzeiten: Für einen ganzen Tag „Ganztägig“ wählen.", overlaps: "Ersetzt die bisherigen Zeiten für", close: "Schließen",
    remove: "Zeitfenster entfernen", cancel: "Abbrechen", apply: "Übernehmen",
  },
  en: {
    short: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
    long: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    week: "Week plan", hours: "Time windows", add: "Add time window", edit: "Edit time window",
    weekdays: "Mon – Fri", weekend: "Sat – Sun", every: "Every day", individual: "Custom",
    preset: "Day selection", days: "Days of the week", none: "No time window", empty: "No delivery days selected.",
    allDay: "All day", from: "From", to: "Until", hour: "Hour", minute: "Minute",
    overnight: "Ends the following day.", equal: "Times are equal. Choose All day for a full day.", overlaps: "Replaces the existing hours for", close: "Close",
    remove: "Remove time window", cancel: "Cancel", apply: "Apply",
  },
};
const presets = { weekdays: dayKeys.slice(0, 5), weekend: dayKeys.slice(5), every: dayKeys };
const presetFor = days => Object.keys(presets).find(k => presets[k].length === days.length && presets[k].every(d => days.includes(d))) || "individual";
const options = count => Array.from({length: count}, (_, i) => {
  const n = String(i).padStart(2, "0"); return `<option value="${n}">${n}</option>`;
}).join("");
const clocks = part => `<fieldset class="clock"><legend data-i="${part}"></legend><div class="time">
  <select id="${part}-hour">${options(24)}</select><span aria-hidden="true">:</span><select id="${part}-minute">${options(60)}</select>
  <button type="button" class="pick-clock" id="${part}-pick">${glyph("clock-outline")}</button></div></fieldset>`;

class DispatcherWeekPicker extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode:"open"});
    this.shadowRoot.innerHTML = `<style>
      :host{display:block;color:var(--nd-text)}${controls}
      h3,legend{font-size:14px;font-weight:600;margin:0}fieldset{border:0;padding:0;margin:0;min-width:0}
      .strip{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:5px;margin:10px 0 18px}
      .strip button{min-width:0;min-height:44px;display:grid;place-content:center;justify-items:center;gap:5px;font-weight:600;border:1px solid var(--nd-line);background:var(--nd-surface);color:var(--nd-muted);border-radius:6px}
      .strip button.on,.strip button[aria-pressed=true]{background:var(--nd-tint);border-color:var(--nd-mark);color:var(--nd-ink)}
      .overview button::after{content:"";height:3px;width:12px;border-radius:2px;background:var(--nd-line)}
      .overview button.on::after{background:var(--nd-ink)}.strip button:hover{border-color:var(--nd-ink)}
      .list-head,.dialog-head,.dialog-foot,.line{display:flex;align-items:center;justify-content:space-between;gap:10px}
      .list-head h3{color:var(--nd-muted)}.list-head .quiet-btn{padding-inline:8px;min-height:36px}
      .rule{display:grid;grid-template-columns:minmax(0,1fr) auto 20px;align-items:center;gap:12px;width:100%;min-height:50px;text-align:left;border-top:1px solid var(--nd-line);padding:7px 5px}
      .rule:hover{background:var(--nd-hover)}.rule span:first-child{font-weight:550}.rule .range{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--nd-muted);font-size:14px}
      .rule ha-icon{--mdc-icon-size:16px;color:var(--nd-muted)}.empty,.note{color:var(--nd-muted);font-size:13px;line-height:1.45;margin:10px 0}
      dialog{width:min(430px,calc(100% - 24px));max-height:calc(100dvh - 32px);overflow:auto;padding:0;margin:auto;border:1px solid var(--nd-line);border-radius:8px;background:var(--nd-surface);color:var(--nd-text);box-shadow:0 16px 48px #0003}
      dialog::backdrop{background:rgba(15,23,28,.46)}.dialog-head,.dialog-foot{padding:12px 18px}.dialog-head{border-bottom:1px solid var(--nd-line)}
      .dialog-head h3{font-size:18px}.dialog-body{padding:20px}.dialog-foot{border-top:1px solid var(--nd-line)}.end{display:flex;gap:6px;margin-left:auto}
      #preset{max-width:54%;min-height:36px;padding:4px 6px;background:var(--nd-surface);color:var(--nd-ink);border:1px solid var(--nd-line);border-radius:5px;font-size:13px}
      .dialog-body .strip{margin-bottom:12px}.allday{display:flex;align-items:center;justify-content:space-between;min-height:46px;border-bottom:1px solid var(--nd-line);cursor:pointer}
      .times{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px}.clock legend{margin-bottom:5px;color:var(--nd-muted);font-size:13px}
      .time{display:flex;align-items:center;gap:0;background:var(--nd-bg);border:1px solid var(--nd-border);border-radius:6px;padding:2px 4px}
      .time select{appearance:none;min-width:0;width:2.15em;height:44px;padding:0;text-align:center;font-size:18px;font-weight:600;font-variant-numeric:tabular-nums;color:var(--nd-text);background:var(--nd-bg);border:0;border-radius:3px}
      .time select:hover{background:var(--nd-hover)}.pick-clock{margin-left:auto;width:34px;height:42px;display:grid;place-items:center;color:var(--nd-muted);padding:0}.pick-clock ha-icon{--mdc-icon-size:17px}
      #remove{color:var(--nd-error)}.dialog-foot .quiet-btn{padding-inline:8px}
      @media(max-width:520px){dialog{inset:auto 0 0;margin:0;width:100%;max-width:none;max-height:92dvh;border-radius:8px 8px 0 0;padding-bottom:env(safe-area-inset-bottom)}
        .dialog-body{padding:16px}.dialog-foot,.dialog-head{padding:9px 12px}.strip{gap:3px}.rule{gap:7px}.times{gap:10px}}
    </style>
      <h3 data-i="week"></h3><div class="strip overview" role="group"></div>
      <div class="list-head"><h3 data-i="hours"></h3><button type="button" class="quiet-btn" id="add">${glyph("plus")}<span data-i="add"></span></button></div>
      <div id="rules"></div>
      <dialog aria-labelledby="dialog-title"><div class="dialog-head"><h3 id="dialog-title"></h3><button type="button" id="close" class="icon-btn">${glyph("close")}</button></div>
        <div class="dialog-body">
          <div class="line"><h3 data-i="days"></h3><select id="preset">${["individual","weekdays","weekend","every"].map(k=>`<option value="${k}" data-i="${k}"></option>`).join("")}</select></div>
          <div class="strip choice" role="group"></div>
          <label class="allday"><span data-i="allDay"></span><input class="switch" type="checkbox" id="all-day"></label>
          <div class="times">${clocks("from")}${clocks("to")}</div>
          <p id="overnight" class="note" data-i="overnight" hidden></p><p id="equal" class="note" data-i="equal" hidden></p><p id="overlap" class="note" role="status" hidden></p>
        </div><div class="dialog-foot"><button type="button" class="icon-btn" id="remove">${glyph("trash-can-outline")}</button>
          <div class="end"><button type="button" class="quiet-btn" id="cancel" data-i="cancel"></button>
          <button type="button" class="solid-btn" id="apply" data-i="apply"></button></div></div></dialog>`;
    this.$ = s => this.shadowRoot.querySelector(s);
    this.map = {};
    this.w = words.de;
    for (const k of dayKeys) {
      const overview = document.createElement("button");
      overview.type = "button";
      overview.onclick = () => this.open(this.map[k] ? [k] : [], [k], overview);
      this.$(".overview").append(overview);
      const choice = document.createElement("button");
      choice.type = "button";
      choice.onclick = () => { this.selected.has(k) ? this.selected.delete(k) : this.selected.add(k); this.paintDialog(); };
      this.$(".choice").append(choice);
    }
    this.$("#add").onclick = e => this.open([], [], e.currentTarget);
    for (const id of ["close", "cancel"]) this.$("#"+id).onclick = () => this.close();
    this.$("#preset").onchange = e => {
      if (presets[e.target.value]) this.selected = new Set(presets[e.target.value]);
      this.paintDialog();
    };
    this.$("dialog").onchange = () => this.paintDialog();
    for (const part of ["from","to"]) this.$("#"+part+"-pick").onclick = () => {
      const select = this.$("#"+part+"-hour");
      select.focus();
      try { select.showPicker?.(); } catch { /* Native selection remains keyboard accessible. */ }
    };
    this.shadowRoot.addEventListener("input", e => e.stopPropagation());
    this.$("#apply").onclick = () => this.commit(false);
    this.$("#remove").onclick = () => this.commit(true);
    this.paint();
  }
  set language(locale) {
    const w = (locale || "de").startsWith("de") ? words.de : words.en;
    if (this.w !== w) { this.w = w; this.paint(); if (this.$("dialog").open) this.paintDialog(); }
  }
  set value(map) {
    this.close(); this.map = {...map}; this.original = []; this.selected = new Set(); this.trigger = null;
    this.$("#all-day").checked = false;
    for (const select of this.shadowRoot.querySelectorAll(".time select")) select.selectedIndex = 0;
    this.paint(); this.paintDialog();
  }
  get value() { return {...this.map}; }
  set disabled(v) {
    if (v) this.close();
    this.inert = v;
  }
  disconnectedCallback() { this.close(); }
  close() { if (this.$("dialog").open) this.$("dialog").close(); }
  label(days) {
    const preset = presetFor(days);
    return preset !== "individual" ? this.w[preset] : days.map(k => this.w[days.length === 1 ? "long" : "short"][dayKeys.indexOf(k)]).join(", ");
  }
  range(win) {
    if (!win) return this.w.none;
    const [a,b] = win.split("-");
    return a === b ? this.w.allDay : a + " – " + b + (b < a ? " (+1)" : "");
  }
  paint() {
    const w = this.w;
    for (const el of this.shadowRoot.querySelectorAll("[data-i]")) el.textContent = w[el.dataset.i];
    this.$(".overview").setAttribute("aria-label", w.week);
    this.$(".choice").setAttribute("aria-label", w.days);
    for (const [i,k] of dayKeys.entries()) {
      const el = this.$(".overview").children[i];
      el.textContent = w.short[i]; el.classList.toggle("on", !!this.map[k]);
      el.title = w.long[i] + ": " + this.range(this.map[k]);
      el.setAttribute("aria-label", el.title);
      el.setAttribute("aria-haspopup", "dialog");
      const day = this.$(".choice").children[i];
      day.textContent = w.short[i]; day.setAttribute("aria-label", w.long[i]);
    }
    const list = this.$("#rules");
    list.replaceChildren();
    const groups = new Map();
    for (const k of dayKeys) if (this.map[k]) {
      const win = this.map[k]; if (!groups.has(win)) groups.set(win, []); groups.get(win).push(k);
    }
    for (const [win, days] of groups) {
      const row = document.createElement("button"); row.type = "button"; row.className = "rule";
      row.innerHTML = '<span></span><span class="range"></span>' + glyph("pencil-outline");
      row.firstChild.textContent = this.label(days); row.children[1].textContent = this.range(win);
      row.title = w.edit + ": " + this.label(days); row.setAttribute("aria-label", row.title); row.setAttribute("aria-haspopup", "dialog");
      row.onclick = () => this.open(days, days, row); list.append(row);
    }
    if (!groups.size) { const p=document.createElement("p"); p.className="empty"; p.textContent=w.empty; list.append(p); }
    for (const id of ["close","remove"]) { this.$("#"+id).title=w[id]; this.$("#"+id).setAttribute("aria-label",w[id]); }
    this.$("#preset").setAttribute("aria-label",w.preset);
    for (const part of ["from","to"]) { const button=this.$("#"+part+"-pick"); button.title=w[part]+" · "+w.hour; button.setAttribute("aria-label",button.title); }
    for (const part of ["from","to"]) for (const unit of ["hour","minute"]) this.$("#"+part+"-"+unit).setAttribute("aria-label",w[part]+" · "+w[unit]);
  }
  open(original, selected, trigger) {
    this.original = original; this.selected = new Set(selected); this.trigger = trigger;
    const win = this.map[original[0]] || (selected.length && selected.every(k=>dayKeys.indexOf(k)>=5) ? "09:00-22:00" : "08:00-22:00");
    const [a,b] = win.split("-");
    this.$("#all-day").checked = a === b;
    for (const [part, time] of [["from",a],["to",b]]) {
      const [hh,mm]=time.split(":"); this.$("#"+part+"-hour").value=hh; this.$("#"+part+"-minute").value=mm;
    }
    this.paintDialog(); this.$("dialog").showModal();
    this.$(".choice").children[Math.max(0,dayKeys.indexOf(selected[0]))].focus();
  }
  time(part) { return this.$("#"+part+"-hour").value + ":" + this.$("#"+part+"-minute").value; }
  paintDialog() {
    const w=this.w, chosen=dayKeys.filter(k=>this.selected.has(k)), all=this.$("#all-day").checked;
    this.$("#dialog-title").textContent=this.original.length?w.edit:w.add;
    this.$("#preset").value=presetFor(chosen);
    for (const [i,k] of dayKeys.entries()) this.$(".choice").children[i].setAttribute("aria-pressed",String(this.selected.has(k)));
    this.$(".times").hidden=all; this.$("#overnight").hidden=all||this.time("to")>=this.time("from");
    this.$("#equal").hidden=all||this.time("to")!==this.time("from");
    const overwritten=chosen.filter(k=>this.map[k] && !this.original.includes(k) && this.map[k]!==this.newWindow());
    this.$("#overlap").hidden=!overwritten.length;
    this.$("#overlap").textContent=overwritten.length ? w.overlaps+" "+this.label(overwritten)+"." : "";
    this.$("#remove").hidden=!this.original.length;
    this.$("#apply").disabled=!chosen.length || (!all && this.time("from")===this.time("to"));
  }
  newWindow() { return this.$("#all-day").checked ? "00:00-00:00" : this.time("from")+"-"+this.time("to"); }
  commit(remove) {
    if (!remove && this.$("#apply").disabled) return;
    for (const k of this.original) delete this.map[k];
    if (!remove) for (const k of this.selected) this.map[k]=this.newWindow();
    this.close(); this.paint();
    (this.trigger?.isConnected ? this.trigger : this.$("#add")).focus();
    this.dispatchEvent(new Event("input",{bubbles:true,composed:true}));
  }
}
if (!customElements.get("dispatcher-week-picker")) customElements.define("dispatcher-week-picker", DispatcherWeekPicker);
