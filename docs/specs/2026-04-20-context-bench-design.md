# context-bench – Design Spec
**Version:** 1.1
**Datum:** 2026-04-20
**Autor:** David Miko (nessos666)
**Status:** Approved (v1.1 – Codex-reviewed, kritische Bugs gefixt)

---

## Ziel

Ein selbstlernender Claude Code Hook der automatisch erkennt womit du arbeitest und den richtigen Kontext lädt — ohne dass du etwas konfigurierst oder erklärst.

**Tagline:** *"Your AI editor knows what you're working on — automatically."*

---

## Das Problem das es löst

Jede Claude Code Session fängt bei Null an. Du musst erklären woran du arbeitest, welche Dateien relevant sind, was der Stand ist. Das kostet Zeit und Tokens.

Existierende Tools (Context7, claude-mem, context-mode) lösen Teilprobleme — aber keines analysiert die erste Nachricht und lädt automatisch die richtigen Projektdateien ohne User-Input.

---

## Wie es funktioniert

```
1. Du tippst deine erste Nachricht
2. UserPromptSubmit Hook feuert (bevor Claude antwortet)
3. context-bench liest Prompt aus stdin (JSON: input_data["prompt"])
4. Keyword-Matching gegen ~/.context-bench/projects.json
5. Relevante Dateien werden gelesen (max. 8.000 Zeichen)
6. Kontext wird als additionalContext injiziert (unsichtbar für User)
7. Claude antwortet bereits mit vollem Projekt-Kontext
8. PostToolUse Hook trackt geänderte Dateien (Write/Edit/MultiEdit)
9. SessionEnd Hook: beobachtete Änderungen → aktualisiert projects.json
```

---

## Architektur

### Einzige Datei: `context_bench.py`

Ein einzelnes Python-Script. Keine externen Dependencies. Läuft als Claude Code Hook (mehrere Events, gleiche Datei).

**Drei Verantwortlichkeiten:**
1. **Matcher** — analysiert Prompt (`UserPromptSubmit`), findet passendes Topic via match_score
2. **Loader** — liest relevante Dateien, baut Context-String, gibt `additionalContext` zurück
3. **Learner** — trackt Änderungen via `PostToolUse`, aktualisiert confidence in `SessionEnd`

### Hook-Events

| Event | Was context-bench macht |
|---|---|
| `UserPromptSubmit` | Prompt lesen (stdin JSON), match, inject additionalContext |
| `PostToolUse` (Write/Edit/MultiEdit) | Geänderte Dateipfade in `~/.context-bench/session_changes.json` merken |
| `SessionEnd` | session_changes.json auswerten → confidence updaten → aufräumen |

### Claude Code Hook Input/Output

**Input (stdin JSON für UserPromptSubmit):**
```json
{
  "session_id": "abc123",
  "transcript_path": "/tmp/claude-transcript-abc123.jsonl",
  "prompt": "Ich möchte den API-Endpoint fixen"
}
```

**Output (stdout JSON für additionalContext):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "## Projekt-Kontext (auto-geladen)\n\nTopic: api\nDateien:\n\n### src/api/routes.py\n[Dateiinhalt...]\n\n### config/api.yaml\n[Inhalt...]"
  }
}
```

Unsichtbar für den User — Claude sieht es, du nicht.

### Lern-Datenbank: `~/.context-bench/projects.json`

```json
{
  "version": 1,
  "projects": [
    {
      "id": "api",
      "keywords": ["api", "endpoint", "route", "fastapi"],
      "root": "/home/user/myproject",
      "paths": ["src/api/", "config/api.yaml"],
      "confidence": 0.87,
      "uses": 14,
      "last_used": "2026-04-20",
      "created": "2026-04-01"
    }
  ],
  "settings": {
    "max_context_chars": 8000,
    "min_confidence_threshold": 0.3,
    "match_threshold": 0.5,
    "decay_days": 30
  }
}
```

**Wichtig:** `root` = absoluter Pfad zum Repo-Root. `paths` sind root-relative Pfade. Verhindert Konflikte zwischen mehreren Projekten mit gleicher Struktur (z.B. `src/api/`).

### Match-Score vs. Confidence

- **match_score** = kurzlebiger Wert pro Anfrage: Anteil der Topic-Keywords die im Prompt vorkommen (0.0–1.0). Wird nicht gespeichert.
- **confidence** = dauerhafter Lernwert: wie zuverlässig dieses Topic für diesen User ist. Wird in `projects.json` gespeichert und verändert sich über Zeit.
- Wenn `match_score >= match_threshold (0.5)` → Topic wird als Treffer gewertet
- Wenn kein Topic `match_score >= 0.5` erreicht → kein Kontext injiziert, neues Topic wird evaluiert

### Selbst-Bootstrap beim ersten Start

Wenn `projects.json` noch nicht existiert — schnell und latenz-bewusst:
1. Scannt nur das aktuelle Verzeichnis (max. 2 Ebenen tief, Timeout: 200ms)
2. Erkennt Sprache/Framework (pyproject.toml, package.json, go.mod etc.)
3. Erkennt Ordnerstruktur (src/, tests/, docs/, config/)
4. Baut erste `projects.json` mit `confidence: 0.5`
5. Verbessert sich ab dem ersten echten Use

Bootstrap läuft lazy: blockiert `UserPromptSubmit` nicht. Wenn Bootstrap länger als 200ms dauert → abbrechen, leere `projects.json` anlegen.

---

## Dateistruktur (GitHub Repo)

```
context-bench/
├── context_bench.py        ← Hook-Script (alles in einer Datei)
├── install.sh              ← Ein-Befehl-Installation
├── uninstall.sh            ← Sauberes Entfernen
├── README.md               ← Dokumentation
├── CONTRIBUTING.md         ← Contribution Guide
├── LICENSE                 ← MIT
├── .github/
│   └── workflows/
│       └── tests.yml       ← CI: pytest auf Python 3.9–3.12, Linux+macOS
├── tests/
│   └── test_context_bench.py
└── examples/
    ├── python-project.json     ← Beispiel projects.json
    ├── node-project.json
    └── rust-project.json
```

---

## Installation

```bash
git clone https://github.com/nessos666/context-bench
cd context-bench
./install.sh
```

`install.sh` macht genau 3 Dinge:
1. Kopiert `context_bench.py` → `~/.context-bench/context_bench.py`
2. Legt `~/.context-bench/` an
3. Trägt Hook-Einträge in `~/.claude/settings.json` ein:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "python3 ~/.context-bench/context_bench.py prompt" }] }
    ],
    "PostToolUse": [
      { "matcher": "Write|Edit|MultiEdit", "hooks": [{ "type": "command", "command": "python3 ~/.context-bench/context_bench.py track" }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "python3 ~/.context-bench/context_bench.py learn" }] }
    ]
  }
}
```

`uninstall.sh` entfernt alle 3 Hook-Einträge aus `settings.json` und löscht `~/.context-bench/`.

**Keine weiteren Dependencies.** Python ist überall vorhanden.

---

## Lern-System

### Confidence-Score

Jedes Topic hat einen `confidence`-Wert (0.0 – 1.0):

| Ereignis | Änderung |
|---|---|
| Topic wurde gematcht, Dateien injiziert | +0.05 |
| Injizierte Dateien wurden in Session geändert | +0.15 |
| Topic gematcht, aber keine injizierten Dateien geändert | -0.05 |
| Topic 30 Tage nicht genutzt | -0.01/Tag |

*Hinweis: Delta-Werte sind provisorisch und werden nach echten Nutzungsdaten kalibriert.*

Wenn `confidence < 0.3` → Topic wird aus `projects.json` entfernt.

### Neues Topic erkennen

Wenn kein bestehendes Topic `match_score >= 0.5` erreicht:
1. Häufige Keywords aus Prompt extrahieren
2. `PostToolUse`-Tracking beobachtet welche Dateien geändert werden
3. Bei `SessionEnd`: neues Topic anlegen mit `confidence: 0.5`, `root` = cwd
4. Wächst oder stirbt durch echte Nutzung

### Session-Tracking

`PostToolUse` schreibt geänderte Pfade in `~/.context-bench/session_changes.json`:
```json
{
  "session_id": "abc123",
  "matched_topic": "api",
  "changed_files": ["src/api/routes.py", "tests/test_routes.py"]
}
```

`SessionEnd` liest diese Datei, vergleicht mit injizierten Dateien des Topics, updated `confidence`, löscht `session_changes.json`.

---

## Edge Cases

| Situation | Verhalten |
|---|---|
| Kein Match gefunden | Kein Kontext injiziert, Session normal |
| Dateien zu groß (>8000 Zeichen) | Truncation mit Hinweis |
| projects.json korrupt | Neu anlegen, Fehler in `~/.context-bench/error.log` |
| Hook-Fehler | `exit 0` — niemals Claude blockieren |
| Leere Nachricht | Kein Kontext, weiter |
| projects.json file lock (gleichzeitiger Zugriff) | Atomic write via temp-file + rename |
| Gespeicherter Pfad wurde gelöscht | Warnung in error.log, Datei aus Topic entfernen |
| Zwei Projekte mit identischer Struktur | `root`-Feld trennt sie eindeutig |
| Bootstrap dauert >200ms | Abbrechen, leere projects.json, nächste Session |

---

## Veröffentlichung

Nach Fertigstellung:
1. **GitHub:** `nessos666/context-bench` (MIT License) — primärer Kanal
2. **Reddit:** r/ClaudeAI, r/artificial — Ankündigung
3. **awesome-claude-code:** PR wenn Liste existiert
4. **Anthropic Community Forum** — Vorstellung im Hooks-Thread

*Hinweis: Smithery, PulseMCP und MCP Registry sind für MCP-Server gedacht — das ist ein Claude Code Hook, kein MCP-Server. Wenn v2 als MCP-Server gebaut wird, sind diese Kanäle relevant.*

---

## Was es einzigartig macht

Kein existierendes Tool kombiniert:
- ✅ Automatische erste-Nachricht-Analyse
- ✅ Selbstlernend ohne manuelle Konfiguration
- ✅ Zero-Dependency (nur Python)
- ✅ Unsichtbare Injektion (kein User-Overhead)
- ✅ Ein-Befehl-Installation
- ✅ Multi-Hook-Architektur (inject + track + learn)

---

## Nicht im Scope (v1)

- Kein MCP-Server (kommt in v2 wenn Nachfrage besteht)
- Kein Support für andere Editoren (Cursor etc.) — Community kann portieren
- Kein Cloud-Sync von projects.json
- Kein Web-UI
- Kein Embedding/Vektor-Matching (simples Keyword-Matching reicht für v1)
