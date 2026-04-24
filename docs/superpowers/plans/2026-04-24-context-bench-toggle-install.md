# context-bench Toggle & Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** context-bench produktiv installieren — Hooks in settings.json eintragen, An/Aus-Skills erstellen, und das bestehende DISABLED-Flag mit Tests absichern.

**Architecture:** DISABLED-Flag (`~/.context-bench/DISABLED`) als technischer Schalter — Hook prueft beim Start, ob die Datei existiert, und macht `exit 0`. Zwei Claude Code Skills (`/ctx-bench-an`, `/ctx-bench-aus`) als bequemer Schalter. Hooks werden via `install.sh` idempotent in `~/.claude/settings.json` eingetragen.

**Tech Stack:** Python 3.9+, pytest, bash

---

## Was schon getan wurde (nicht nochmal bauen!)

- `context_bench.py`: DISABLED-Check nach Mode-Validierung eingebaut (commit d3b0503)
- `install.sh`: timeout 5/10 zu Hook-Registrierung hinzugefuegt (commit d3b0503)
- `~/.context-bench/projects.json`: Duplikate bereinigt, leere DB

---

## File Map

| Datei | Aktion | Zweck |
|---|---|---|
| `tests/test_context_bench.py` | Modify | Tests fuer DISABLED-Flag Verhalten hinzufuegen |
| `~/.claude/commands/ctx-bench-an.md` | Create | Skill: DISABLED loeschen |
| `~/.claude/commands/ctx-bench-aus.md` | Create | Skill: DISABLED erstellen |
| `~/.claude/settings.json` | Modify (via install.sh) | Hooks registrieren |

---

### Task 1: Tests fuer DISABLED-Flag

**Files:**
- Modify: `tests/test_context_bench.py` (am Ende anhaengen)

- [ ] **Step 1: Failing-Tests schreiben**

Am Ende von `tests/test_context_bench.py` anhaengen:

```python
# ── Task 10: DISABLED flag ────────────────────────────────────────────────────
import tempfile


def test_prompt_exits_zero_when_disabled(monkeypatch, capsys):
    """prompt gibt {} aus und laeuft durch wenn DISABLED existiert."""
    with tempfile.TemporaryDirectory() as tmpdir:
        disabled = os.path.join(tmpdir, "DISABLED")
        Path(disabled).touch()
        monkeypatch.setattr(
            "context_bench.Path.home", lambda: Path(tmpdir)
        )
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(json.dumps({"prompt": "fix the api", "session_id": "d-s1"})),
        )
        with pytest.raises(SystemExit) as exc:
            from context_bench import main
            import sys as _sys
            _sys.argv = ["context_bench.py", "prompt"]
            main()
        assert exc.value.code == 0


def test_learn_cleans_up_session_when_disabled(tmp_path, monkeypatch):
    """learn raeumt Session-Datei auf, auch wenn DISABLED aktiv ist."""
    session_dir = str(tmp_path / "sessions")
    # Session vorab anlegen
    save_session("d-s2", "api", [], "fix", [], session_dir=session_dir)
    assert load_session("d-s2", session_dir=session_dir) is not None

    # DISABLED-Flag setzen
    disabled = tmp_path / "DISABLED"
    disabled.touch()
    monkeypatch.setattr("context_bench.Path.home", lambda: tmp_path)

    monkeypatch.setattr(
        "sys.stdin", io.StringIO(json.dumps({"session_id": "d-s2"}))
    )
    import sys as _sys
    _sys.argv = ["context_bench.py", "learn"]
    with pytest.raises(SystemExit) as exc:
        from importlib import reload
        import context_bench as cb
        _sys.argv = ["context_bench.py", "learn"]
        cb.main()
    assert exc.value.code == 0
    # Session muss weg sein
    assert load_session("d-s2", session_dir=session_dir) is None


def test_track_exits_zero_when_disabled(tmp_path, monkeypatch):
    """track macht sofort exit 0 wenn DISABLED existiert."""
    disabled = tmp_path / "DISABLED"
    disabled.touch()
    monkeypatch.setattr("context_bench.Path.home", lambda: tmp_path)
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {"session_id": "d-s3", "tool_input": {"file_path": "/tmp/x.py"}}
            )
        ),
    )
    import sys as _sys
    _sys.argv = ["context_bench.py", "track"]
    with pytest.raises(SystemExit) as exc:
        from context_bench import main
        main()
    assert exc.value.code == 0
```

- [ ] **Step 2: Tests laufen lassen — muessen FEHLSCHLAGEN (wegen Path.home monkeypatch)**

```bash
cd /home/boobi/HAUPTLAGER/05_Strategien_Entwicklung/context-bench
python3 -m pytest tests/test_context_bench.py -k "disabled" -v
```

Erwartet: Tests schlagen fehl oder laufen nicht wie erwartet — das zeigt was noch fehlt.

- [ ] **Step 3: Tests anpassen bis sie gruenbleibt**

Die Tests nutzen `monkeypatch` auf `context_bench.Path.home`. Falls der Patch nicht greift (weil `Path.home` eine classmethod ist), alternativer Ansatz: DISABLED-Pfad als Env-Variable uebergeben oder direkte Datei in `tmp_path` anlegen und den `_DEFAULT_DB_DIR` patchen:

```python
monkeypatch.setattr("context_bench._DEFAULT_DB_DIR", str(tmp_path))
```

Dann DISABLED-Flag als `tmp_path / "DISABLED"` anlegen. Passe alle drei Tests entsprechend an.

- [ ] **Step 4: Alle 53+3 = 56 Tests muessen gruen sein**

```bash
python3 -m pytest tests/ -q
```

Erwartet: `56 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_context_bench.py
git commit -m "test: add DISABLED flag behavior tests (prompt/track/learn)"
```

---

### Task 2: Skill-Dateien erstellen

**Files:**
- Create: `~/.claude/commands/ctx-bench-an.md`
- Create: `~/.claude/commands/ctx-bench-aus.md`

- [ ] **Step 1: ctx-bench-aus.md erstellen**

Datei anlegen: `~/.claude/commands/ctx-bench-aus.md`

```markdown
---
description: context-bench deaktivieren (DISABLED-Flag setzen)
---

Fuehre folgende Bash-Befehle aus:

```bash
mkdir -p ~/.context-bench && touch ~/.context-bench/DISABLED
```

Gib danach aus: "context-bench deaktiviert — naechste Session kein Kontext-Injection."
```

- [ ] **Step 2: ctx-bench-an.md erstellen**

Datei anlegen: `~/.claude/commands/ctx-bench-an.md`

```markdown
---
description: context-bench aktivieren (DISABLED-Flag loeschen)
---

Fuehre folgende Bash-Befehle aus:

```bash
rm -f ~/.context-bench/DISABLED
```

Gib danach aus: "context-bench aktiv — naechste Session injiziert Kontext automatisch."
```

- [ ] **Step 3: Skill-Dateien verifizieren**

```bash
ls -la ~/.claude/commands/ctx-bench-*.md
cat ~/.claude/commands/ctx-bench-aus.md
cat ~/.claude/commands/ctx-bench-an.md
```

Erwartet: Beide Dateien vorhanden, Inhalt korrekt.

- [ ] **Step 4: Commit (Skills werden nicht ins Repo committed — sind User-lokal)**

Keine Git-Aktion noetig. Skills liegen in `~/.claude/commands/`, ausserhalb des Repos.

---

### Task 3: Hooks in settings.json installieren

**Files:**
- Modify: `~/.claude/settings.json` (via install.sh)

- [ ] **Step 1: Aktuellen Zustand von settings.json pruefen**

```bash
python3 -c "
import json
with open('/home/boobi/.claude/settings.json') as f:
    cfg = json.load(f)
hooks = cfg.get('hooks', {})
print('UserPromptSubmit:', len(hooks.get('UserPromptSubmit', [])), 'Eintraege')
print('PostToolUse:', len(hooks.get('PostToolUse', [])), 'Eintraege')
print('SessionEnd:', len(hooks.get('SessionEnd', [])), 'Eintraege')
# context-bench bereits drin?
import json as j
s = j.dumps(hooks)
print('context-bench bereits registriert:', 'context_bench.py' in s)
"
```

Erwartet: `context-bench bereits registriert: False`

- [ ] **Step 2: install.sh ausfuehren**

```bash
cd /home/boobi/HAUPTLAGER/05_Strategien_Entwicklung/context-bench
bash install.sh
```

Erwartet:
```
Installing context-bench...
Hooks registered in /home/boobi/.claude/settings.json
context-bench installed!
  Script: /home/boobi/.context-bench/context_bench.py
  Data:   /home/boobi/.context-bench
  Hooks:  /home/boobi/.claude/settings.json
```

- [ ] **Step 3: Hooks verifizieren**

```bash
python3 -c "
import json
with open('/home/boobi/.claude/settings.json') as f:
    cfg = json.load(f)
hooks = cfg.get('hooks', {})
import json as j
s = j.dumps(hooks, indent=2)
# Nur context-bench Eintraege zeigen
lines = [l for l in s.splitlines() if 'context_bench' in l or 'timeout' in l]
for l in lines:
    print(l)
"
```

Erwartet: 3 Zeilen mit `context_bench.py` (prompt/track/learn) + 3 Zeilen mit `timeout`.

- [ ] **Step 4: Idempotenz-Test — kein Doppel-Eintrag bei zweitem Aufruf**

```bash
bash install.sh
python3 -c "
import json
with open('/home/boobi/.claude/settings.json') as f:
    cfg = json.load(f)
hooks = cfg.get('hooks', {})
s = json.dumps(hooks)
count = s.count('context_bench.py')
print(f'context_bench.py Vorkommen: {count} (erwartet: 3)')
assert count == 3, f'FEHLER: {count} statt 3!'
print('Idempotenz OK')
"
```

Erwartet: `Idempotenz OK`

---

### Task 4: Smoke-Test End-to-End

- [ ] **Step 1: context-bench ausschalten via Skill-Datei direkt testen**

```bash
mkdir -p ~/.context-bench && touch ~/.context-bench/DISABLED
echo '{"prompt": "fix the api", "session_id": "smoke-1"}' | \
  python3 /home/boobi/.context-bench/context_bench.py prompt
echo "Exit code: $?"
```

Erwartet: Kein Output (oder leere Zeile), `Exit code: 0`

- [ ] **Step 2: context-bench einschalten**

```bash
rm -f ~/.context-bench/DISABLED
echo '{"prompt": "fix the api", "session_id": "smoke-2"}' | \
  python3 /home/boobi/.context-bench/context_bench.py prompt
echo "Exit code: $?"
```

Erwartet: JSON-Output (`{}` da noch kein passendes Projekt in projects.json), `Exit code: 0`

- [ ] **Step 3: context_router.py weiterhin unveraendert pruefen**

```bash
grep -c "context_bench" /home/boobi/.claude/settings.json
grep -c "context_router" /home/boobi/.claude/settings.json
```

Erwartet: Beide geben `1` aus — beide Hooks registriert, keiner hat den anderen ueberschrieben.

- [ ] **Step 4: Abschliessende Test-Suite**

```bash
cd /home/boobi/HAUPTLAGER/05_Strategien_Entwicklung/context-bench
python3 -m pytest tests/ -q
```

Erwartet: Alle Tests gruen (56 oder mehr).

- [ ] **Step 5: Abschluss-Commit im Repo**

```bash
git add -A
git status  # nur docs/ Aenderungen erwartet
git commit -m "docs: add toggle & install implementation plan"
```
