# Portable Neo4j helper for Windows (no Docker required).
# Usage (PowerShell):
#   .\scripts\neo4j_local.ps1 start
#   .\scripts\neo4j_local.ps1 status
#   .\scripts\neo4j_local.ps1 stop
#   .\scripts\neo4j_local.ps1 browser

param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "status", "browser")]
    [string]$Action = "status"
)

$NEO4J_HOME = "D:\neo4j\neo4j-community-2026.05.0"
$JAVA_HOME = "D:\neo4j\jdk-21.0.12+8"
$PID_FILE = "$NEO4J_HOME\neo4j.pid"

switch ($Action) {
    "start" {
        if (Test-Path $PID_FILE) {
            $old = Get-Content $PID_FILE
            if (Get-Process -Id $old -ErrorAction SilentlyContinue) {
                Write-Host "Neo4j already running (pid $old)."
                exit 0
            }
        }
        $env:JAVA_HOME = $JAVA_HOME
        $proc = Start-Process -FilePath "$NEO4J_HOME\bin\neo4j.bat" -ArgumentList "console" `
            -WorkingDirectory $NEO4J_HOME -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput "$NEO4J_HOME\logs\console.out.log" `
            -RedirectStandardError "$NEO4J_HOME\logs\console.err.log"
        Set-Content -Path $PID_FILE -Value $proc.Id
        Write-Host "Starting Neo4j (pid $($proc.Id))..."
        $ok = $false
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 2
            if (Test-NetConnection -ComputerName 127.0.0.1 -Port 7687 -WarningAction SilentlyContinue -InformationLevel Quiet) {
                $ok = $true
                break
            }
        }
        if ($ok) { Write-Host "Neo4j ready: http://localhost:7474 (bolt 7687)" } else { Write-Host "Neo4j did not become ready; check logs\neo4j.log" }
    }
    "stop" {
        if (Test-Path $PID_FILE) {
            $pid_ = Get-Content $PID_FILE
            Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
            Remove-Item $PID_FILE -Force -ErrorAction SilentlyContinue
            Write-Host "Neo4j stopped."
        } else {
            Write-Host "No pid file; stop java processes manually if needed."
        }
    }
    "status" {
        $bolt = Test-NetConnection -ComputerName 127.0.0.1 -Port 7687 -WarningAction SilentlyContinue -InformationLevel Quiet
        $http = Test-NetConnection -ComputerName 127.0.0.1 -Port 7474 -WarningAction SilentlyContinue -InformationLevel Quiet
        Write-Host "bolt 7687: $bolt | http 7474: $http"
    }
    "browser" {
        Write-Host "Neo4j Browser: http://localhost:7474"
        Write-Host "Bolt: bolt://localhost:7687 | user: neo4j | password: jobgraph_neo4j_2026"
    }
}
