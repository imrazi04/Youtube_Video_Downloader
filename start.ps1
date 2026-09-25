# Starts the downloader on this PC and opens a public Cloudflare Tunnel link to it.
# Run with: start.bat (double-click), or
#           powershell -ExecutionPolicy Bypass -File start.ps1
# Close this window (or press Ctrl+C) to stop both.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) { $cloudflared = "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe" }
if (-not (Test-Path $cloudflared)) {
    Write-Host "cloudflared is not installed. Install it with:" -ForegroundColor Red
    Write-Host "    winget install --id Cloudflare.cloudflared"
    exit 1
}

$log    = Join-Path $env:TEMP "ytdl-cloudflared.log"
$server = Start-Process python -ArgumentList "serve.py" -NoNewWindow -PassThru
$tunnel = Start-Process $cloudflared -ArgumentList "tunnel --no-autoupdate --url http://localhost:5000" `
                        -NoNewWindow -PassThru -RedirectStandardError $log

try {
    # The quick tunnel prints its random public URL to its log
    $url = $null
    for ($i = 0; $i -lt 45 -and -not $url; $i++) {
        Start-Sleep -Seconds 1
        $match = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue |
                 Select-Object -First 1
        if ($match) { $url = $match.Matches[0].Value }
    }

    if ($url) {
        try { Set-Clipboard -Value $url } catch {}
        Write-Host ""
        Write-Host "  Public link (copied to clipboard):" -ForegroundColor Green
        Write-Host "  $url" -ForegroundColor Cyan
        Write-Host "  Local link: http://localhost:5000"
        Write-Host "  Keep this window open. The link changes every time you restart." -ForegroundColor Yellow
        Write-Host ""
    } else {
        Write-Host "Could not get a tunnel link - see $log. The app still runs at http://localhost:5000" -ForegroundColor Red
    }

    Wait-Process -Id $server.Id
}
finally {
    foreach ($p in @($server, $tunnel)) {
        if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
}
