param(
    [Parameter(Mandatory = $true)]
    [string]$ReleaseTag
)

$ErrorActionPreference = 'Stop'
$platformRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $platformRoot 'frontend'
$evidenceRoot = Join-Path $platformRoot "release-evidence\$ReleaseTag"
$testDatabase = 'aftertime_release_gate'

New-Item -ItemType Directory -Force -Path $evidenceRoot | Out-Null

function Invoke-GateStep {
    param([string]$Name, [scriptblock]$Action)
    Write-Host "`n[release] $Name" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "Release gate failed: $Name" }
}

Push-Location $platformRoot
try {
    Invoke-GateStep 'Frontend regression tests' {
        Push-Location $frontendRoot
        try { npm test } finally { Pop-Location }
    }
    Invoke-GateStep 'Frontend production build' {
        Push-Location $frontendRoot
        try { npm run build } finally { Pop-Location }
    }
    Invoke-GateStep 'Frontend dependency audit' {
        Push-Location $frontendRoot
        try { npm audit --audit-level=high } finally { Pop-Location }
    }
    Invoke-GateStep 'Container images' { docker compose build api worker frontend }
    Invoke-GateStep 'Backend regression tests' {
        docker compose run --rm api python -m pytest -q
    }

    docker compose exec -T postgres dropdb --if-exists -U aftertime $testDatabase
    docker compose exec -T postgres createdb -U aftertime $testDatabase
    try {
        Invoke-GateStep 'Clean database migration' {
            docker compose run --rm -e "DATABASE_URL=postgresql+psycopg://aftertime:aftertime-local@postgres:5432/$testDatabase" api alembic upgrade head
        }
    }
    finally {
        docker compose exec -T postgres dropdb --if-exists -U aftertime $testDatabase
    }

    Invoke-GateStep 'Development database migration' {
        docker compose run --rm api alembic upgrade head
    }
    Invoke-GateStep 'Runtime startup' {
        docker compose up -d --force-recreate api worker frontend
    }
    Invoke-GateStep 'Simulation queue health' {
        $redisReply = (docker compose exec -T redis redis-cli ping).Trim()
        if ($redisReply -ne 'PONG') { throw "Redis health check failed: $redisReply" }

        $workerId = (docker compose ps -q worker).Trim()
        if (-not $workerId) { throw 'Simulation worker container is missing' }
        $workerState = (docker inspect --format '{{.State.Status}}' $workerId).Trim()
        if ($workerState -ne 'running') {
            throw "Simulation worker is not running: $workerState"
        }
    }

    $healthy = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://localhost:8000/health' -TimeoutSec 2
            if ($health.status -eq 'ok') { $healthy = $true; break }
        }
        catch { Start-Sleep -Seconds 1 }
    }
    if (-not $healthy) { throw 'Release gate failed: API health timeout' }

    $workspace = Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/lab/workspace' -TimeoutSec 10
    if ($workspace.version.architecture_version -lt 2) { throw 'Workspace is not architecture v2' }
    if ($workspace.observables.Count -lt 1) { throw 'Observable catalog is empty' }
    if ($workspace.event_types.Count -lt 1) { throw 'Event type catalog is empty' }
    if ($workspace.monitors.Count -lt 1) { throw 'Monitor template is missing' }

    Invoke-GateStep 'Git diff integrity' { git diff --check }

    $evidence = [ordered]@{
        releaseTag = $ReleaseTag
        testedAt = (Get-Date).ToUniversalTime().ToString('o')
        commit = (git rev-parse HEAD)
        architectureVersion = $workspace.version.architecture_version
        observables = $workspace.observables.Count
        eventTypes = $workspace.event_types.Count
        status = 'passed'
    }
    $evidence | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $evidenceRoot 'release-gate.json')
    Write-Host "`nRelease gate PASSED: $ReleaseTag" -ForegroundColor Green
}
finally {
    Pop-Location
}
