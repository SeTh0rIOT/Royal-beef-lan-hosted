#!/usr/bin/env python3
"""
Royal Beef LAN — Mini-Server.

Liefert die Seite aus und speichert den Turnierstand als eine JSON-Datei,
damit alle Geraete im Netz denselben Stand sehen.

Nur Python-Standardbibliothek, keine Abhaengigkeiten.

  PORT       Port im Container            (Standard 8080)
  WEB_ROOT   Ordner mit der index.html    (Standard /app/web)
  DATA_FILE  Ablage des Turnierstands     (Standard /data/state.json)
  WRITE_PASSWORD  Passwort fuer Aenderungen. Leer = jeder darf schreiben
                  (nur im eigenen LAN vertretbar). Sobald gesetzt, ist es
                  auch das Admin-Passwort der Oberflaeche.
  EDIT_LEASE      Sekunden, die ein Bearbeitungsrecht ohne Lebenszeichen
                  gilt (Standard 120).

Damit sich zwei Admins nicht gegenseitig ueberschreiben, darf immer nur ein
Geraet schreiben. Wer das Recht hat, behaelt es, solange er aktiv ist; ein
anderes Geraet kann es bewusst uebernehmen.
"""

import hmac
import http.server
import json
import os
import shutil
import socketserver
import threading
import time
from datetime import datetime

PORT = int(os.environ.get("PORT", "8080"))
WEB_ROOT = os.environ.get("WEB_ROOT", "/app/web")
DATA_FILE = os.environ.get("DATA_FILE", "/data/state.json")
WRITE_PASSWORD = os.environ.get("WRITE_PASSWORD", "")
LEASE = int(os.environ.get("EDIT_LEASE", "120"))

_lock = threading.Lock()
_store = {"rev": 0, "state": None}
_editor = {"id": None, "ts": 0.0}


def editor_active():
    return bool(_editor["id"]) and (time.time() - _editor["ts"]) < LEASE


def editor_info():
    if not editor_active():
        return {"id": None, "age": 0}
    return {"id": _editor["id"], "age": int(time.time() - _editor["ts"])}
_saves_since_backup = 0


def load_state():
    global _store
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and "rev" in data:
            _store = data
            print(f"[royalbeef] Stand geladen, Revision {_store['rev']}", flush=True)
    except FileNotFoundError:
        print("[royalbeef] Noch kein Stand vorhanden, starte leer", flush=True)
    except Exception as exc:
        print(f"[royalbeef] Stand nicht lesbar ({exc}), starte leer", flush=True)


def write_state():
    """Atomar schreiben, damit ein Absturz mitten im Speichern nichts zerreisst."""
    global _saves_since_backup
    folder = os.path.dirname(DATA_FILE) or "."
    os.makedirs(folder, exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_store, fh, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)

    # Alle 20 Speichervorgaenge eine datierte Sicherung ablegen.
    _saves_since_backup += 1
    if _saves_since_backup >= 20:
        _saves_since_backup = 0
        try:
            stamp = datetime.now().strftime("%Y%m%d-%H%M")
            shutil.copyfile(DATA_FILE, os.path.join(folder, f"backup-{stamp}.json"))
        except Exception:
            pass


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_ROOT, **kwargs)

    # ---------- Hilfsfunktionen ----------
    def send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # Die Seite selbst nie zwischenspeichern, sonst haengen Clients
        # nach einem Update auf der alten Fassung fest.
        if self.path in ("/", "/index.html"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    # ---------- Routen ----------
    def route(self):
        return self.path.split("?")[0].rstrip("/") or "/"

    def check_password(self):
        """Vergleich in konstanter Zeit, damit sich das Passwort nicht erraten laesst."""
        given = self.headers.get("X-Royalbeef-Auth", "")
        return hmac.compare_digest(given, WRITE_PASSWORD)

    def read_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            return None

    def do_GET(self):
        if self.route() == "/api/state":
            with _lock:
                return self.send_json(200, dict(
                    _store, protected=bool(WRITE_PASSWORD), editor=editor_info()))
        return super().do_GET()

    def do_POST(self):
        route = self.route()

        if route == "/api/auth":
            if not WRITE_PASSWORD:
                return self.send_json(200, {"ok": True, "protected": False})
            if self.check_password():
                return self.send_json(200, {"ok": True, "protected": True})
            return self.send_json(401, {"ok": False, "protected": True})

        # Bearbeitungsrecht anfordern
        if route == "/api/lock":
            if WRITE_PASSWORD and not self.check_password():
                return self.send_json(401, {"error": "kein Schreibrecht"})
            body = self.read_body()
            if body is None or not body.get("client"):
                return self.send_json(400, {"error": "client fehlt"})
            cid = body["client"]
            with _lock:
                if editor_active() and _editor["id"] != cid and not body.get("takeover"):
                    return self.send_json(409, editor_info())
                _editor["id"] = cid
                _editor["ts"] = time.time()
                return self.send_json(200, {"holder": cid})

        # Bearbeitungsrecht zurueckgeben
        if route == "/api/unlock":
            body = self.read_body() or {}
            with _lock:
                if _editor["id"] == body.get("client"):
                    _editor["id"] = None
                    _editor["ts"] = 0.0
            return self.send_json(200, {"ok": True})

        return self.send_error(404)

    def do_PUT(self):
        if self.route() != "/api/state":
            return self.send_error(404)
        if WRITE_PASSWORD and not self.check_password():
            return self.send_json(401, {"error": "kein Schreibrecht"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
        except Exception:
            return self.send_json(400, {"error": "kein gueltiges JSON"})

        state = body.get("state")
        if not isinstance(state, dict) or not isinstance(state.get("players"), list):
            return self.send_json(400, {"error": "unerwarteter Aufbau"})

        cid = body.get("client")
        with _lock:
            # Nur ein Geraet darf gleichzeitig schreiben.
            if editor_active() and _editor["id"] != cid:
                return self.send_json(423, editor_info())

            client_rev = body.get("rev")
            # Wer auf einem veralteten Stand sitzt, darf nicht ueberschreiben.
            if _store["rev"] and client_rev != _store["rev"]:
                return self.send_json(409, dict(_store, editor=editor_info()))

            _store["state"] = state
            _store["rev"] = _store["rev"] + 1
            if cid:                       # Schreiben verlaengert das Recht
                _editor["id"] = cid
                _editor["ts"] = time.time()
            write_state()
            return self.send_json(200, {"rev": _store["rev"]})

    def log_message(self, fmt, *args):
        pass  # Zugriffe nicht mitloggen, das Log bleibt sonst unlesbar


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    load_state()
    if WRITE_PASSWORD:
        print("[royalbeef] Aenderungen sind passwortgeschuetzt", flush=True)
    else:
        print("[royalbeef] WARNUNG: kein WRITE_PASSWORD gesetzt, jeder darf schreiben", flush=True)
    print(f"[royalbeef] laeuft auf Port {PORT}, Seite aus {WEB_ROOT}", flush=True)
    with Server(("", PORT), Handler) as httpd:
        httpd.serve_forever()
