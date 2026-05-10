# Home Assistant Notification Dispatcher

Eine Custom Integration fuer Home Assistant, die Benachrichtigungen zentral an Personen verteilt.

## Was sie kann

- Personenprofile in der Home-Assistant-UI verwalten
- pro Person eine `person.*` Entitaet und eine oder mehrere `notify.*` Mobile-App-Ziele hinterlegen
- Zustellung nach Typ steuern: `critical`, `warning`, `info`, `reminder`
- Werktage und Wochenende getrennt aktivieren und mit Zeitfenstern versehen
- DND-Zeit pro Person konfigurieren
- optional nur zustellen, wenn die Person zuhause ist
- optionaler Fallback pro Person, wenn ein direkter Empfaenger gerade nicht erreichbar ist
- kritische Nachrichten immer zustellen, unabhaengig von Zeit, DND und Anwesenheit
- Icons vor dem Titel und persistente Home-Assistant-Benachrichtigung fuer `warning` und `critical`

Die Action erwartet im Kern:

1. `title`
2. `message`
3. `type`: `critical`, `info`, `warning` oder `reminder`
4. `target`: `all` oder ein in der UI konfigurierter Target-Name wie `johannes`

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

Als Notify-Ziel kannst du klassische Mobile-App-Actions wie `notify.mobile_app_johans_iphone` oder moderne Notify-Entitaeten wie `notify.johans_iphone` eintragen. Mehrere Ziele werden mit Komma getrennt.

Jede Person bekommt einen eigenen Target-Namen, z.B. `johannes` oder `linda`. Der Name `all` ist reserviert. Wenn eine Person einen Fallback-Target-Namen bekommt, wird eine direkte Nachricht an diese Person an den Fallback geschickt, falls sie wegen Abwesenheit, Zeitfenster oder DND gerade nicht erreichbar ist.

## Action nutzen

```yaml
action: notification_dispatcher.send
data:
  title: "Waschmaschine"
  message: "Die Waesche ist fertig."
  type: reminder
  target: all
```

Nur bestimmte Personen:

```yaml
action: notification_dispatcher.send
data:
  title: "Tuere"
  message: "Die Haustuer steht offen."
  type: warning
  target: johannes
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
  target: all
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
  target: all
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
