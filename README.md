# Home Assistant Notification Dispatcher

Eine Custom Integration fuer Home Assistant, die Benachrichtigungen zentral an Personen verteilt.

## Was sie kann

- Personenprofile in der Home-Assistant-UI verwalten
- pro Person eine `person.*` Entitaet und eine oder mehrere `notify.*` Mobile-App-Ziele hinterlegen
- Zustellung nach Typ steuern: `critical`, `warning`, `info`, `reminder`
- Werktage und Wochenende getrennt aktivieren und mit Zeitfenstern versehen
- DND-Zeit pro Person konfigurieren
- optional nur zustellen, wenn die Person zuhause ist
- kritische Nachrichten immer zustellen, unabhaengig von Zeit, DND und Anwesenheit

Die Action erwartet im Kern:

1. `title`
2. `message`
3. `type`: `critical`, `info`, `warning` oder `reminder`
4. `target_all` oder `target`: alle Personen oder ausgewaehlte `person.*` Entitaeten

## Installation

1. Kopiere `custom_components/notification_dispatcher` in den `custom_components` Ordner deiner Home-Assistant-Konfiguration.
2. Starte Home Assistant neu.
3. Oeffne **Einstellungen > Geraete & Dienste > Integration hinzufuegen**.
4. Suche nach **Notification Dispatcher**.
5. Oeffne danach die Optionen der Integration und fuege Personen hinzu.

Als Notify-Ziel kannst du klassische Mobile-App-Actions wie `notify.mobile_app_johans_iphone` oder moderne Notify-Entitaeten wie `notify.johans_iphone` eintragen. Mehrere Ziele werden mit Komma getrennt.

## Action nutzen

```yaml
action: notification_dispatcher.send
data:
  title: "Waschmaschine"
  message: "Die Waesche ist fertig."
  type: reminder
  target_all: true
```

Nur bestimmte Personen:

```yaml
action: notification_dispatcher.send
data:
  title: "Tuere"
  message: "Die Haustuer steht offen."
  type: warning
  target_all: false
  target:
    - person.johan
```

Kritisch:

```yaml
action: notification_dispatcher.send
data:
  title: "Alarm"
  message: "Rauchmelder im Flur ausgeloest."
  type: critical
  target_all: true
```

Zusatzdaten fuer die Mobile-App kannst du weiterreichen:

```yaml
action: notification_dispatcher.send
data:
  title: "Garage"
  message: "Das Garagentor ist noch offen."
  type: warning
  data:
    tag: garage-door
    group: security
```

Fuer einen Testlauf ohne Versand:

```yaml
action: notification_dispatcher.send
response_variable: dispatcher_result
data:
  title: "Test"
  message: "Wuerde so zugestellt werden."
  type: info
  target_all: true
  dry_run: true
```

## Entwicklung auf GitHub

Empfohlener Start:

```powershell
git init
git add .
git commit -m "Initial notification dispatcher integration"
git branch -M main
git remote add origin https://github.com/jesterrace-666/ha-notification-dispatcher.git
git push -u origin main
```

Die GitHub Action kompiliert die Integration bei Pushes und Pull Requests.
