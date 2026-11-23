// Shared controls use the active Home Assistant theme in each panel shadow root.
export const glyph = name => `<ha-icon icon="mdi:${name}" aria-hidden="true"></ha-icon>`;
export const controls = `
  *,*::before,*::after{box-sizing:border-box} [hidden]{display:none!important}
  button,select,input{font:inherit;letter-spacing:0} button,select{cursor:pointer}
  button{color:inherit;background:transparent;border:0} button:disabled{cursor:default;opacity:.5}
  :focus-visible{outline:2px solid var(--nd-ink);outline-offset:3px}
  ha-icon{display:inline-flex;align-items:center;justify-content:center;flex:none;width:var(--mdc-icon-size,20px);height:var(--mdc-icon-size,20px);--mdc-icon-size:20px}
  .icon-btn{width:40px;height:40px;padding:0;border-radius:6px;display:inline-grid;place-items:center;color:var(--nd-muted)}
  .icon-btn:hover:not(:disabled),.quiet-btn:hover:not(:disabled){background:var(--nd-hover)}
  .solid-btn,.quiet-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:40px;padding:6px 14px;border-radius:6px;font-size:14px;font-weight:600}
  .solid-btn{background:var(--nd-action);color:var(--nd-on-action)}.solid-btn:hover:not(:disabled){filter:brightness(.94)}
  .quiet-btn{color:var(--nd-ink)} .solid-btn ha-icon,.quiet-btn ha-icon{--mdc-icon-size:17px}
  .switch{appearance:none;-webkit-appearance:none;position:relative;width:40px;height:24px;min-width:40px;flex:none;margin:0;border:1px solid var(--nd-border);border-radius:20px;background:var(--nd-off);cursor:pointer}
  .switch::after{content:"";position:absolute;left:3px;top:3px;width:16px;height:16px;border-radius:50%;background:var(--nd-muted)}
  .switch:checked{background:var(--nd-action);border-color:var(--nd-action)}.switch:checked::after{left:19px;background:var(--nd-on-action)}
  @media(forced-colors:active){.switch{appearance:auto}.switch::after{display:none} [aria-pressed=true],[aria-selected=true]{outline:2px solid Highlight}}
`;
