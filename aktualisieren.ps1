# ── Prisma: Pipeline auf Knopfdruck ──────────────────────────────────────────
# Aufruf: Rechtsklick → "Mit PowerShell ausführen"  ODER  im Terminal: .\aktualisieren.ps1
#
# Voraussetzung: ntfy-App auf dem Handy installiert und Topic abonniert
#   → https://ntfy.sh  (kostenlos, kein Account nötig)
#   → In der App: Topic  prisma-update  abonnieren

$NTFY_TOPIC = "prisma-update-steffen"   # ← hier dein eigenes Topic eintragen (muss einzigartig sein)
$PROJEKT    = $PSScriptRoot             # Projektordner automatisch ermitteln

function Sende-Nachricht($titel, $text, $prio = "default") {
    try {
        Invoke-RestMethod -Uri "https://ntfy.sh/$NTFY_TOPIC" `
            -Method POST `
            -Headers @{ Title = $titel; Priority = $prio; Tags = "newspaper" } `
            -Body $text -ErrorAction SilentlyContinue | Out-Null
    } catch {}
}

Write-Host ""
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  PRISMA – Aktualisierung gestartet    " -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

Set-Location $PROJEKT

# ── 1. Feeds laden ────────────────────────────────────────────────────────────
Write-Host "[ 1/3 ]  RSS-Feeds abrufen …" -ForegroundColor Yellow
python fetch_feeds.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER beim Feeds-Abruf!" -ForegroundColor Red
    Sende-Nachricht "Prisma ❌ Fehler" "Feeds konnten nicht geladen werden." "high"
    exit 1
}

# ── 2. Themen clustern ────────────────────────────────────────────────────────
Write-Host "[ 2/3 ]  Themen clustern …" -ForegroundColor Yellow
python cluster_topics.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER beim Clustering!" -ForegroundColor Red
    Sende-Nachricht "Prisma ❌ Fehler" "Clustering fehlgeschlagen." "high"
    exit 1
}

# ── 3. Framing analysieren ────────────────────────────────────────────────────
Write-Host "[ 3/3 ]  Framing analysieren (dauert ein paar Minuten) …" -ForegroundColor Yellow
python analyze_framing.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "FEHLER bei der Framing-Analyse!" -ForegroundColor Red
    Sende-Nachricht "Prisma ❌ Fehler" "Framing-Analyse fehlgeschlagen." "high"
    exit 1
}

# ── Datenbank committen & pushen ──────────────────────────────────────────────
Write-Host ""
Write-Host "  Datenbank auf GitHub hochladen …" -ForegroundColor Yellow

$datum = Get-Date -Format "yyyy-MM-dd HH:mm"
git add data/news_agent.db
git commit -m "Daten: Tagesupdate $datum"
git push origin master

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "═══════════════════════════════════════" -ForegroundColor Green
    Write-Host "  ✓ Fertig! Render deployt automatisch." -ForegroundColor Green
    Write-Host "═══════════════════════════════════════" -ForegroundColor Green
    Sende-Nachricht "Prisma ✅ aktualisiert" "Neue Themen sind live – viel Spaß beim Lesen!" "default"
} else {
    Write-Host "Push fehlgeschlagen – bitte Token prüfen." -ForegroundColor Red
    Sende-Nachricht "Prisma ⚠️ Push fehlgeschlagen" "Daten wurden analysiert, aber nicht hochgeladen." "high"
}
