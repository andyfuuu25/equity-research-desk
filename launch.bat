@echo off
setlocal
title Equity Research Desk
cd /d "%~dp0"

echo.
echo   ==============================================
echo     EQUITY RESEARCH DESK  -  one-click launcher
echo   ==============================================
echo.

rem ---------- locate Node.js ----------
where node >nul 2>nul
if %errorlevel%==0 goto node_ok
if exist "C:\Program Files\nodejs\node.exe" (
    set "PATH=C:\Program Files\nodejs;%PATH%"
    goto node_ok
)
echo   [X] Node.js not found. Install it from https://nodejs.org and re-run.
pause
exit /b 1
:node_ok

rem ---------- locate Python ----------
where python >nul 2>nul
if %errorlevel%==0 goto py_ok
echo   [X] Python not found. Install it from https://python.org and re-run.
pause
exit /b 1
:py_ok

rem ---------- first run: API keys ----------
if exist "backend\.env" goto env_ok
echo   First-time setup. The app needs a free Google Gemini API key.
echo   Get one at: https://aistudio.google.com/apikey
echo.
set "GKEY="
set /p GKEY=  Paste your Gemini API key and press Enter:
if not defined GKEY (
    echo   [X] No key entered - the report generator cannot run without one.
    pause
    exit /b 1
)
echo.
echo   Optional: an Alpha Vantage key adds sentiment-tagged news.
echo   Without it, headlines still load from Yahoo Finance - no key needed.
set "AVKEY="
set /p AVKEY=  Paste an Alpha Vantage key, or press Enter to skip:
echo.
echo   Save keys on this computer for future runs?
echo   y = save to backend\.env so you are never asked again
echo   N = session only: keys live in memory and wipe automatically
echo       when you close the server windows  (default)
set "SAVEKEYS="
set /p SAVEKEYS=  Save? [y/N]:
if /i "%SAVEKEYS%"=="y" goto save_keys
goto session_only
:save_keys
> "backend\.env"  echo GEMINI_API_KEY=%GKEY%
>> "backend\.env" echo ALPHA_VANTAGE_API_KEY=%AVKEY%
echo.
echo   Keys saved to backend\.env  - edit that file to change them later.
echo.
goto env_ok
:session_only
rem Keys are handed to the server processes as environment variables only.
rem Nothing touches disk; they vanish when the server windows close.
set "GEMINI_API_KEY=%GKEY%"
set "ALPHA_VANTAGE_API_KEY=%AVKEY%"
echo.
echo   Session-only mode: nothing saved. Keys wipe when you close the
echo   server windows, and you will be asked again on the next launch.
echo.
:env_ok

rem ---------- dependencies (installed on first run only) ----------
if exist "frontend\node_modules" goto fe_ok
echo   Installing frontend dependencies - this happens once...
pushd frontend
call npm install
popd
if not exist "frontend\node_modules" (
    echo   [X] npm install failed. Check your internet connection and re-run.
    pause
    exit /b 1
)
:fe_ok

python -c "import fastapi, uvicorn, yfinance, statsmodels, dotenv; from google import genai" >nul 2>nul
if %errorlevel%==0 goto be_ok
echo   Installing backend dependencies - this happens once...
pip install -r backend\requirements.txt
:be_ok

rem ---------- start both servers ----------
echo   Starting backend  -  http://localhost:8000
start "Research Desk - Backend" cmd /k python -m uvicorn main:app --app-dir backend --port 8000

echo   Starting frontend -  http://localhost:3000
start "Research Desk - Frontend" cmd /k node frontend\node_modules\next\dist\bin\next dev frontend

rem ---------- open the app ----------
echo   Waiting for servers to come up...
timeout /t 8 /nobreak >nul
start "" http://localhost:3000

echo.
echo   =====================================================
echo    The app is running. KEEP THIS WINDOW OPEN.
echo    Press any key here to STOP the app when you finish.
echo   =====================================================
pause >nul

rem ---------- shutdown ----------
echo.
echo   Stopping servers...
taskkill /FI "WINDOWTITLE eq Research Desk - Backend*" /T /F >nul 2>nul
taskkill /FI "WINDOWTITLE eq Research Desk - Frontend*" /T /F >nul 2>nul

rem Offer to wipe a saved key on the way out. Session-only mode has nothing
rem on disk, so the question is skipped entirely.
if not exist "backend\.env" goto shutdown_done
echo.
echo   A saved API key exists in backend\.env.
echo   y = wipe it now  (you will be asked for it on the next launch)
echo   N = keep it for next time  (default)
set "WIPEKEY="
set /p WIPEKEY=  Wipe the saved API key? [y/N]:
if /i not "%WIPEKEY%"=="y" goto keep_key
del /q "backend\.env"
echo   Key wiped from disk.
goto shutdown_done
:keep_key
echo   Key kept for next launch.
:shutdown_done
echo.
echo   App stopped. This window will close in a few seconds.
timeout /t 4 >nul
exit /b 0
