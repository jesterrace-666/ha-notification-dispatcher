# Notification Dispatcher

Central notification dispatcher for Home Assistant.

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
