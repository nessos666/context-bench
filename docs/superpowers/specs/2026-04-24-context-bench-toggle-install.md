# context-bench – Toggle & Install Spec
**Version:** 1.0
**Datum:** 2026-04-24
**Autor:** David Miko (nessos666)
**Status:** Approved

---

## Ziel

context-bench korrekt installieren (Hooks in settings.json), einen sicheren An/Aus-Schalter einbauen, und sauber parallel zu context_router.py betreiben.

---

## Kontext

- `~/.context-bench/` existiert bereits (projects.json, sessions/)
- Hooks sind noch NICHT in `~/.claude/settings.json` eingetragen
- `context_router.py` läuft bereits bei UserPromptSubmit (FSS-System für Trading)
- projects.json enthält Test-Duplikate die bereinigt werden müssen

---

## Architektur-Entscheidungen

### 1. Parallel mit context_router.py

context-bench und context_router.py laufen am gleichen UserPromptSubmit Event. Kein Konflikt, weil:
- context_router.py ist handgepflegt, spezifisch für TRADINGPROJEKT
- context-bench ist generisch, lernt alle anderen Projekte
- TRADINGPROJEKT wird nicht in projects.json aufgenommen

### 2. Toggle: Presence-File + Skills

**Technischer Schalter:** `~/.context-bench/DISABLED`
- Datei existiert → Hook macht sofort `exit 0`, kein Kontext injiziert
- Datei fehlt → Hook läuft normal

**Bequemer Schalter:** Zwei Claude Code Skills
- `/ctx-bench-an` → löscht DISABLED-Datei, gibt Bestätigung aus
- `/ctx-bench-aus` → erstellt DISABLED-Datei, gibt Bestätigung aus

Fail-safe: Wenn Python kaputt ist, funktioniert `touch ~/.context-bench/DISABLED` trotzdem.

---

## Was zu bauen ist

### A) Disable-Check in context_bench.py

Nach Mode-Validierung, vor dem Dispatch (nicht literal erste Zeile — sonst werden ungueltige Aufrufe maskiert wenn disabled):

```python
# Nach: mode = sys.argv[1] + Validierung dass mode in ("prompt","track","learn")
_disabled_flag = Path.home() / ".context-bench" / "DISABLED"
if _disabled_flag.exists():
    if mode == "learn":
        # Cleanup laeuft trotzdem — sonst bleiben session files liegen
        try:
            raw = sys.stdin.read()
            data = json.loads(raw) if raw.strip() else {}
            session_id = data.get("session_id", "")
            if session_id:
                cleanup_session(session_id)
        except Exception:
            pass
    sys.exit(0)
```

Wichtig: `learn` raeumt auch im disabled-Zustand auf. `prompt` und `track` machen sofort `exit 0`.

### B) Zwei Skill-Dateien

`~/.claude/commands/ctx-bench-an.md`:
```
Loesche ~/.context-bench/DISABLED falls vorhanden.
Gib aus: "context-bench aktiv"
```

`~/.claude/commands/ctx-bench-aus.md`:
```
mkdir -p ~/.context-bench (sicherstellen dass Verzeichnis existiert).
Erstelle ~/.context-bench/DISABLED (leere Datei).
Gib aus: "context-bench deaktiviert"
```

Hinweis: mkdir -p noetig, falls context-bench noch nicht installiert war.

### C) Hooks in settings.json eintragen

Via `install.sh` (idempotent — `already_registered()` verhindert Duplikate). Format mit Pfad-Quotes und Timeouts:

```json
"UserPromptSubmit": [
  { "hooks": [{ "type": "command", "command": "python3 \"/home/user/.context-bench/context_bench.py\" prompt", "timeout": 5 }] }
],
"PostToolUse": [
  { "matcher": "Write|Edit|MultiEdit", "hooks": [{ "type": "command", "command": "python3 \"/home/user/.context-bench/context_bench.py\" track", "timeout": 5 }] }
],
"SessionEnd": [
  { "hooks": [{ "type": "command", "command": "python3 \"/home/user/.context-bench/context_bench.py\" learn", "timeout": 10 }] }
]
```

- Pfade gequotet (sicher bei $HOME mit Leerzeichen)
- `timeout: 5/10` (verhindert blockierende Hooks)
- `already_registered()` prueft vor Eintrag — kein Doppel-Eintrag bei Reinstall
- Bestehende Hooks (context_router.py etc.) bleiben unveraendert

### D) projects.json bereinigen

Duplikate entfernen. Leere, valide projects.json zurueckschreiben:

```json
{
  "version": 1,
  "projects": [],
  "settings": {
    "max_context_chars": 8000,
    "min_confidence_threshold": 0.3,
    "match_threshold": 0.5,
    "decay_days": 30
  }
}
```

TRADINGPROJEKT wird nicht eingetragen (context_router.py zustaendig).

---

## Reihenfolge

1. context_bench.py: Disable-Check einbauen + Tests
2. projects.json bereinigen
3. Hooks in settings.json eintragen
4. Skill-Dateien erstellen
5. Smoke-Test: `/ctx-bench-aus` → Prompt senden → kein Kontext → `/ctx-bench-an` → Prompt senden → Kontext erscheint

---

## Was nicht geaendert wird

- context_bench.py Kern-Logik (Matcher, Loader, Learner) bleibt unveraendert
- context_router.py bleibt unveraendert
- TRADINGPROJEKT-Kontext wird nicht in context-bench migriert

---

## Erfolgskriterium

- `touch ~/.context-bench/DISABLED` → naechste Session kein context-bench Kontext
- `rm ~/.context-bench/DISABLED` → context-bench laeuft wieder
- `/ctx-bench-aus` + `/ctx-bench-an` funktionieren als Skills
- context_router.py laeuft weiterhin unveraendert
- Alle bestehenden Tests (53/53) bleiben gruen
