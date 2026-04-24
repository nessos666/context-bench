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

Ganz oben in `main()` (vor jeder anderen Logik):

```python
DISABLED_FLAG = Path.home() / ".context-bench" / "DISABLED"
if DISABLED_FLAG.exists():
    sys.exit(0)
```

Gilt fuer alle drei Subcommands: `prompt`, `track`, `learn`.

### B) Zwei Skill-Dateien

`~/.claude/commands/ctx-bench-an.md`:
```
Loesche ~/.context-bench/DISABLED falls vorhanden.
Gib aus: "context-bench aktiv"
```

`~/.claude/commands/ctx-bench-aus.md`:
```
Erstelle ~/.context-bench/DISABLED (leere Datei).
Gib aus: "context-bench deaktiviert"
```

### C) Hooks in settings.json eintragen

Drei Eintraege in `~/.claude/settings.json` unter `"hooks"`:

```json
"UserPromptSubmit": [
  { "hooks": [{ "type": "command", "command": "python3 ~/.context-bench/context_bench.py prompt" }] }
],
"PostToolUse": [
  { "matcher": "Write|Edit|MultiEdit", "hooks": [{ "type": "command", "command": "python3 ~/.context-bench/context_bench.py track" }] }
],
"SessionEnd": [
  { "hooks": [{ "type": "command", "command": "python3 ~/.context-bench/context_bench.py learn" }] }
]
```

Bestehende Hooks bleiben unveraendert erhalten.

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
