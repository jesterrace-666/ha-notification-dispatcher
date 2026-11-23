# Home Assistant Notification Dispatcher

Eine Custom Integration fuer Home Assistant, die Benachrichtigungen zentral an Personen verteilt.

## Release-Linie

Ab Version `1.0.0` traegt die `1.x`-Linie den Beinamen `Herald`.
Der technische Name bleibt unveraendert:

- Integration: `Notification Dispatcher`
- Domain: `notification_dispatcher`
- Action: `notification_dispatcher.send`

## Was sie kann

- Personenprofile in der Home-Assistant-UI verwalten
- pro Person eine `person.*` Entitaet und eine oder mehrere vorhandene `notify.*` Ziele auswaehlen
- fest eingebautes Ziel `all`/`alle`, das alle konfigurierten Personen auswaehlt
- fest eingebaute, nicht loeschbare Gruppe `Fallback` fuer Umleitungen
- eigene Gruppen aus Personen anlegen, z.B. `familie`
- Zustellung nach Typ steuern: `critical`, `warning`, `info`, `reminder`
- Werktage und Wochenende mit kompakten Zeitfenstern wie `08:00-22:00` versehen
- alternativ rund um die Uhr zustellen; gespeicherte Ruhezeiten berücksichtigen
- optional nur zustellen, wenn die Person zuhause ist
- kritische Nachrichten immer zustellen, unabhaengig von Zeit, DND und Anwesenheit
- automatische Fallback-Zustellung: wenn ein Ziel wegen Zeitfenster, DND oder Zuhause-Pruefung nicht erreicht wird
- Icons vor dem Titel und persistente Home-Assistant-Benachrichtigung fuer `warning` und `critical`

Die Action erwartet im Kern:

1. `title`
2. `message`
3. `type`: `critical`, `info`, `warning` oder `reminder`
4. `target`: Personen, Dispatcher-Gruppen, `alle` oder `system`. Mehrere Ziele sind kombinierbar. Bei `critical` erreicht die Nachricht immer alle konfigurierten Personen.

## Benachrichtigen

Unter **Seitenleiste → Benachrichtigen → Verlauf** siehst du die letzten 50 Dispatcher-Nachrichten, die für dich bestimmt waren, einschließlich weitergeleiteter und nicht zugestellter Nachrichten. Bestehende Lesezeichen auf `/notification-verlauf` funktionieren weiterhin. Es ist keine Änderung an bestehenden Automationen nötig. Der Verlauf beginnt nach dem Update auf 1.6.0; Testläufe und reine Systemmeldungen erzeugen keinen persönlichen Eintrag.

- Dein HA-Benutzerkonto muss mit deiner konfigurierten HA-Person verknüpft sein. Ohne diese Zuordnung bleibt der Verlauf leer. Jeder sieht nur seine eigenen Nachrichten, auch Administratoren. Ein später verknüpftes Konto übernimmt keinen fremden Verlauf.
- Eine blockierte Nachricht nennt den Grund (etwa Ruhezeit, Zeitfenster oder Zuhause-Regel) und den tatsächlichen Ausgang der Weiterleitung. „Übergeben“ bedeutet, dass der Notify-Aufruf erfolgreich war; es ist keine Empfangsbestätigung vom Handy.
- Der Fallback-Push beginnt z. B. mit **FB: @Linda**. Bei mehreren ursprünglichen Empfängern bleibt der Titel kurz (**FB: @Linda +1**); im eigenen Verlauf der Vertretung stehen die Namen, aber keine fremden Standort- oder Ruhezeitgründe.
- Der Verlauf bleibt bei HA-Neustarts erhalten und wird beim Entfernen der Integration gelöscht. Die HA-Glocke für dauerhafte Systemmeldungen bleibt davon unabhängig.

### Meine Erreichbarkeit

Unter **Benachrichtigen → Meine Erreichbarkeit** bearbeitest du dein eigenes Dispatcher-Profil, auch ohne Adminrechte. Ab **1.9.0 Herald** zeigt der **Wochenplan** alle sieben Tage. Tippe auf einen Tag, um nur diesen zu ändern, oder auf ein Zeitfenster, um alle zugehörigen Tage gemeinsam zu bearbeiten. **Zeitfenster hinzufügen** bietet freie Mehrfachauswahl sowie die Vorauswahl **Mo–Fr**, **Sa–So** und **Alle Tage**. Jeder Tag kann ein eigenes Fenster haben. Beim Übernehmen siehst du, welche Tage aus einem anderen Fenster übernommen werden.

Wähle Anfang und Ende minutengenau oder **Ganztägig**. Ein Fenster Montag 22:00 bis 06:00 gilt bis Dienstagmorgen, nicht schon Montagfrüh. Ohne eigenes Fenster gibt es nur dann eine reguläre Zustellung, wenn das Fenster des Vortags noch läuft. Bestehende Werktag-/Wochenendpläne behalten bis zur ersten Zeitänderung ihr bisheriges Verhalten. Mit **24/7** pausierst du den Wochenplan, ohne ihn zu verlieren. **Nur wenn zuhause** gilt weiterhin; Info, Warnung und Erinnerung sind einzeln wählbar, neue kritische Meldungen gehen immer durch.

**Speichern** wirkt sofort, auch für Fallback und bereits vorgemerkte persönliche Erinnerungen. 24/7 blendet die Zeitfelder aus und behält die zuletzt gespeicherten Fenster. Eine noch wirksame Ruhezeit aus einem älteren Profil wird angezeigt und kann ausdrücklich aufgehoben werden. Geräte, Gruppen und Personenzuordnung bleiben in der Integrationsverwaltung. Ohne eindeutige Verknüpfung deines HA-Kontos mit einer Dispatcher-Person lässt sich hier kein Profil bearbeiten.

### Direkt auf dem Handy antworten

Ab **1.7.0 Herald** kannst du eine Dispatcher-Mitteilung auf dem iPhone gedrückt halten und **Gelesen**, **5 Min.**, **30 Min.** oder **60 Min.** wählen. Android bietet **Gelesen** und **Erinnern ...** an; die zweite Aktion zeigt die drei Zeiten als Schaltflächen in einer weiteren Mitteilung an. Es ist weder eine Bestätigung erforderlich noch eine zusätzliche Automation. Ohne Auswahl passiert nichts.

- **Gelesen** markiert nur deinen Eintrag im Notification Verlauf und storniert eine dafür vorgemerkte Erinnerung. Die gemeinsame HA-Systemmeldung und die Nachrichten anderer Personen bleiben unverändert.
- Die Erinnerung geht nur an das Gerät, auf dem du die Zeit gewählt hast. Bei Fälligkeit prüft der Dispatcher deine **aktuellen** Einstellungen: Nachrichtentyp, Anwesenheit, Wochentag und Zeitfenster sowie eine gegebenenfalls aktive Ruhezeit. Wird die Erinnerung blockiert, steht der Grund in deinem Verlauf. Es gibt dabei weder eine Weiterleitung an Fallback noch einen weiteren Systemeintrag.
- Eine **neue kritische Meldung** geht wie bisher sofort an alle. Eine selbst bestellte Wiederholung derselben Meldung berücksichtigt dagegen die persönlichen Zeit- und Ortsregeln.
- Voraussetzung für die Tasten: Die HA-Person und die Companion-App auf dem Zielgerät sind mit demselben HA-Benutzerkonto verknüpft. Andere Notify-Ziele funktionieren unverändert. Eigene Push-Aktionen belegen zuerst die verfügbaren Plätze. Die Tasten gelten für die letzten 50 Nachrichten im persönlichen Verlauf. Bereits vorgemerkte Erinnerungen bleiben auch darüber hinaus und über einen HA-Neustart hinweg erhalten.

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

Beim Hinzufuegen einer Person waehlst du direkt die vorhandene `person.*` Entitaet aus Home Assistant aus. Danach waehlst du ein oder mehrere vorhandene Notify-Ziele aus, zum Beispiel `notify.mobile_app_jmi_iphone`. Falls Home Assistant kein Ziel melden kann oder ein Ziel fehlt, bleibt eine manuelle Eingabe moeglich.

Zeitfenster werden kompakt eingetragen:

- Werktage: `08:00-22:00`
- Wochenende: `09:00-22:00`

Ein leeres Werktag- oder Wochenende-Feld bedeutet: an diesen Tagen nicht zustellen. Für **24/7** musst du keine Uhrzeiten eintragen. Eine in älteren Profilen ausdrücklich hinterlegte Ruhezeit wird beim Versand ebenfalls geprüft.

Das Ziel `all` bzw. `alle` ist immer vorhanden und kann nicht geloescht werden. Zusaetzlich gibt es die feste Gruppe `fallback`, die nicht geloescht werden kann und fuer automatische Umleitungen genutzt wird. Weitere Gruppen kannst du in den Optionen anlegen, zum Beispiel `familie`.

## Action nutzen

### Systemmeldungen

Im Aktionseditor findest du unter **Ziele** den Eintrag **Systemmeldung (dauerhaft)**.
Für einen Update-Hinweis in der HA-Glocke genügt folgende Aktion.

```yaml
action: notification_dispatcher.send
data:
  target: system
  title: "Update verfügbar"
  message: "Für Home Assistant Core gibt es eine neue Version."
```

Für einen zusätzlichen Push an Johannes wählst du beide Ziele oder setzt in YAML
`target: [system, person.johannes]`. Die Glocke zeigt **System** und den Titel,
der Push zeigt den Empfängerkreis. Bei `warning` und `critical` entsteht der
Systemeintrag automatisch genau einmal. Bei gleichem Titel und Typ aktualisiert
der nächste Aufruf denselben Eintrag. Die zurückgegebene
`persistent[0].notification_id` kannst du mit `persistent_notification.dismiss` aufheben.

### Weitere Beispiele

```yaml
action: notification_dispatcher.send
data:
  title: "Waschmaschine"
  message: "Die Waesche ist fertig."
  type: reminder
  target: alle
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

Eine Gruppe:

```yaml
action: notification_dispatcher.send
data:
  title: "Essen"
  message: "Essen ist fertig."
  type: info
  target: familie
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
  target: person.johannes
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
