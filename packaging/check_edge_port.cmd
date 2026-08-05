@echo off
setlocal
title Edge Port 9222 Check

echo Checking port 9222...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$connections = @(Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue); if ($connections.Count -eq 0) { Write-Host 'RESULT: Port 9222 is not listening.' -ForegroundColor Yellow; exit 1 }; $edgeFound = $false; foreach ($connection in $connections) { $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue; $processName = if ($process) { $process.ProcessName } else { 'Unknown' }; $processPath = if ($process -and $process.Path) { $process.Path } else { 'Unavailable' }; Write-Host ('Address: {0}:{1}' -f $connection.LocalAddress, $connection.LocalPort); Write-Host ('Process: {0} (PID {1})' -f $processName, $connection.OwningProcess); Write-Host ('Path: {0}' -f $processPath); if ($processName -eq 'msedge') { $edgeFound = $true } }; if ($edgeFound) { Write-Host 'RESULT: Microsoft Edge is listening on port 9222.' -ForegroundColor Green; exit 0 }; Write-Host 'RESULT: Port 9222 is occupied by a process other than Microsoft Edge.' -ForegroundColor Red; exit 2"

set "check_exit_code=%ERRORLEVEL%"
echo.
pause
exit /b %check_exit_code%
