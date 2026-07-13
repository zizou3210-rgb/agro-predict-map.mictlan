@echo off
setlocal
set SCRIPT=%~dp0desktop_installer.py
if not exist "%SCRIPT%" set SCRIPT=%~dp0installers\desktop_installer.py
set LOGDIR=%LOCALAPPDATA%\Mictlan-AgriXGBoost
set LOGFILE=%LOGDIR%\installer-output.log

if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>nul

echo [installer] Using script: %SCRIPT%
echo [installer] Log file: %LOGFILE%
if not exist "%SCRIPT%" (
  echo [installer] ERROR: desktop_installer.py was not found.
  pause
  exit /b 1
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  echo [installer] Launching installer with py...
  py -3 "%SCRIPT%" --install
  goto end
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
  echo [installer] Launching installer with python...
  python "%SCRIPT%" --install
  goto end
)

echo [installer] ERROR: Python no esta disponible en este sistema.
pause
exit /b 1

:end
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE%==0 (
  echo [installer] Installer finished.
) else (
  echo [installer] Installer failed with exit code %EXITCODE%.
)
echo [installer] Review log: %LOGFILE%
pause
exit /b %EXITCODE%
