@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\nufibox-agent.ps1" %*
exit /b %ERRORLEVEL%
