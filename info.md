# Notification Dispatcher

Central notification dispatcher for Home Assistant.

Starting with version `1.0.0`, the `1.x` release line carries the codename `Herald` while keeping the same integration and service names.

Use this integration to define Home Assistant people once, select one or more existing notify targets for each person, configure compact delivery windows and DND rules, use the built-in all/alle target or your own groups, and call one action from automations:

```yaml
action: notification_dispatcher.send
data:
  title: "Door"
  message: "The front door is open."
  type: warning
  target:
    - person.johannes
```

After installing through HACS, restart Home Assistant and add **Notification Dispatcher** from **Settings > Devices & services**.

Built-in groups:

- `all/alle` (non-removable)
- `fallback` (non-removable): receives rerouted notifications when originally selected recipients are skipped because of schedule, DND, or home checks.

**Herald 1.7:** Mark a Companion push as read or be reminded in 5, 30, or 60 minutes directly from the notification. Personal reminders recheck the recipient's current rules, go only to the requesting device, and never create another system or fallback notification. No changes to automations are required.
