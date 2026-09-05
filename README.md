# Royal Beef LAN

Turnierseite für vier Spiele mit Backups, Rundenwertung, Double Elimination
und gemeinsamem Punktestand. Läuft als kleiner Container im Homelab, alle
Geräte sehen denselben Stand.

## Inhalt des Repositories

| Datei | Zweck |
|---|---|
| `index.html` | Die komplette Seite. Braucht keine Bibliotheken. |
| `server.py` | Liefert die Seite aus und speichert den Turnierstand. Nur Python-Standardbibliothek. |
| `Dockerfile` | Baut beides in ein Image. |
| `docker-compose.yml` | Stack für Portainer. |

Der Turnierstand liegt im Docker-Volume `royalbeef-data` als `state.json`.
Alle 20 Speichervorgänge legt der Server eine datierte Sicherung daneben.

## Einrichten über Portainer

Kein SSH nötig. Die Dateien kommen über die GitHub-Weboberfläche ins
Repository, Portainer holt sie sich von dort.

1. **Repository anlegen.** Auf github.com ein neues Repository erstellen,
   die vier Dateien oben per *Add file → Upload files* hochladen. Public
   reicht — das Passwort landet nicht hier.

2. **Stack in Portainer.** *Stacks → Add stack*, Name `royalbeef`,
   Build method **Repository**:
   * Repository URL: die Adresse deines Repositories
   * Repository reference: `refs/heads/main`
   * Compose path: `docker-compose.yml`

3. **Passwort setzen.** Weiter unten unter *Environment variables* →
   *Add an environment variable*: Name `WRITE_PASSWORD`, Value dein Passwort.
   Das ist ab sofort auch das Admin-Passwort der Seite.

4. **Deploy the stack.** Portainer baut das Image und startet den Container.
   Beim ersten Mal dauert das ein bis zwei Minuten.

5. **Im LAN prüfen** unter `http://DOCKER-IP:8087`. Unten muss ein grüner
   Punkt mit „Live-Sync mit dem Server“ stehen.

6. **Proxy Host im Nginx Proxy Manager**: Domain eintragen, Scheme `http`,
   Forward Hostname die IP des Docker-Hosts, Forward Port `8087`,
   *Block Common Exploits* an. Im Reiter SSL ein Let's-Encrypt-Zertifikat
   holen und *Force SSL* anhaken.

## Aktualisieren

Neue `index.html` im Repository hochladen (*Add file → Upload files*, die
alte wird ersetzt). Dann in Portainer den Stack öffnen und
**Pull and redeploy** klicken. Der Turnierstand im Volume bleibt dabei
erhalten.

Wer es automatisch mag: beim Anlegen des Stacks *GitOps updates* einschalten,
dann prüft Portainer das Repository in einem festen Intervall selbst.

## Passwortschutz

* **Lesen ist frei.** Jeder mit dem Link sieht Punktestand und Turnierbaum.
* **Schreiben nur mit Passwort.** Der Server weist alles andere ab.
* Der Anmeldedialog fragt den Server, nicht die HTML-Datei. Das Passwort
  unter „Einstellungen“ zu ändern wirkt nur im Betrieb ohne Server.

Bleibt `WRITE_PASSWORD` leer, darf jeder schreiben, der den Port erreicht.
Das ist nur im eigenen LAN vertretbar.

## Ohne Server

Die `index.html` funktioniert auch allein — per Doppelklick oder auf GitHub
Pages. Dann speichert sie im Browser statt auf dem Server, ohne Abgleich
zwischen Geräten. Die Seite erkennt das selbst und zeigt es unten an.

## Wenn der Server ausfällt

Die Seite springt auf lokalen Speicher zurück und zeigt das unten an.
Eingaben aus dieser Zeit gehen nicht verloren, sie werden beim nächsten
Speichern wieder hochgeschoben.
