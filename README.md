# Home Assistant Notification Dispatcher

Eine Custom Integration fuer Home Assistant, die Benachrichtigungen zentral an Personen verteilt.

## Was sie kann

- Personenprofile in der Home-Assistant-UI verwalten
- pro Person eine `person.*` Entitaet und eine oder mehrere `notify.*` Mobile-App-Ziele hinterlegen
- Zustellung nach Typ steuern: `critical`, `warning`, `info`, `reminder`
- Werktage und Wochenende mit kompakten Zeitfenstern wie `08:00-22:00` versehen
- DND-Zeit pro Person konfigurieren
- optional nur zustellen, wenn die Person zuhause ist
- kritische Nachrichten immer zustellen, unabhaengig von Zeit, DND und Anwesenheit
- Icons vor dem Titel und persistente Home-Assistant-Benachrichtigung fuer `warning` und `critical`

Die Action erwartet im Kern:

1. `title`
2. `message`
3. `type`: `critical`, `info`, `warning` oder `reminder`
4. `target`: leer/`all` fuer alle oder eine bzw. mehrere `person.*` Entitaeten

## Installation

### HACS

1. Oeffne HACS.
2. Oeffne das Drei-Punkte-Menue oben rechts.
3. Waehle **Custom repositories**.
4. Fuege `https://github.com/jesterrace-666/ha-notification-dispatcher` hinzu.
5. Waehle als Kategorie **Integration**.
6. Installiere **Notification Dispatcher**.
7. Starte Home Assistant neu.
8. Oeffne **Einstellungen > Geraete & Dienste > Integration hinzufuegen** und suche nach **Notification Dispatcher**.

### Manuell

1. Kopiere `custom_components/notification_dispatcher` in den `custom_components` Ordner deiner Home-Assistant-Konfiguration.
2. Starte Home Assistant neu.
3. Oeffne **Einstellungen > Geraete & Dienste > Integration hinzufuegen**.
4. Suche nach **Notification Dispatcher**.
5. Oeffne danach die Optionen der Integration und fuege Personen hinzu.

Beim Hinzufuegen einer Person waehlst du direkt die vorhandene `person.*` Entitaet aus Home Assistant aus. Danach hinterlegst du ein oder mehrere Mobile-App-Ziele. Die Integration bietet vorhandene `notify.*` Ziele an; du kannst aber weiterhin eigene Werte wie `notify.mobile_app_jmi_iphone` eintragen.

Zeitfenster werden kompakt eingetragen:

- Werktage: `08:00-22:00`
- Wochenende: `09:00-22:00`
- Ruhezeit/DND: `22:00-07:00`

Ein leeres Werktag- oder Wochenende-Feld bedeutet: an diesen Tagen nicht zustellen. Eine leere Ruhezeit bedeutet: keine DND-Sperre.

## Action nutzen

```yaml
action: notification_dispatcher.send
data:
  title: "Waschmaschine"
  message: "Die Waesche ist fertig."
  type: reminder
```

Nur bestimmte Personen:

```yaml
action: notification_dispatcher.send
data:
  title: "Tuere"
  message: "Die Haustuer steht offen."
  type: warning
  target:
    - person.johannes
```

Kritisch:

```yaml
action: notification_dispatcher.send
data:
  title: "Alarm"
  message: "Rauchmelder im Flur ausgeloest."
  type: critical
  target: all
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
