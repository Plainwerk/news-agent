@echo off
chcp 65001 >nul
REM ── Prisma: Tagesaktualisierung per Doppelklick ──────────────────────────────
REM Holt Feeds, clustert Themen, analysiert das Framing ueber das Claude-Abo
REM (lokale `claude`-CLI, KEIN API-Key) und pusht die DB zu Render.
REM
REM Doppelklick auf diese Datei genuegt. Voraussetzung:
REM   - Python im PATH
REM   - Claude Code installiert und angemeldet (`claude` im PATH)

cd /d "%~dp0"

REM API-Key aus der Umgebung entfernen, damit die Analyse garantiert ueber das
REM Abo laeuft und nicht ueber einen metered Key abgerechnet wird.
set "ANTHROPIC_API_KEY="

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0aktualisieren.ps1"

echo.
echo Fertig. Fenster kann geschlossen werden.
pause
