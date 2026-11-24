@echo off
echo Stopping Lock In...
curl -s -X POST http://127.0.0.1:47615/api/quit >nul 2>&1
timeout /t 2 >nul
echo Stopped.
pause
