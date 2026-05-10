# Notification Dispatcher

Central notification dispatcher for Home Assistant.

Use this integration to define Home Assistant people once, assign one or more mobile app notify targets to each person, configure compact delivery windows and DND rules, and call one action from automations:

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
