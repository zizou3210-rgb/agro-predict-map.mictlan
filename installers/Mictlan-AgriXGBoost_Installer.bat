@echo off
setlocal
cd /d "%~dp0"

set "SCRIPT="
set "PYTHON_CMD="
set "CANDIDATE1=%~dp0desktop_installer.py"
set "CANDIDATE2=%~dp0installers\desktop_installer.py"

if exist "%CANDIDATE1%" set "SCRIPT=%CANDIDATE1%"
if not defined SCRIPT if exist "%CANDIDATE2%" set "SCRIPT=%CANDIDATE2%"

set "LOGDIR=%LOCALAPPDATA%\Mictlan-AgriXGBoost"
set "LOGFILE=%LOGDIR%\installer-output.log"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>nul

echo [installer] Working directory: %CD%
echo [installer] Candidate 1: %CANDIDATE1%
echo [installer] Candidate 2: %CANDIDATE2%
echo [installer] Log file: %LOGFILE%

if not defined SCRIPT (
  echo [installer] ERROR: desktop_installer.py was not found.
  echo [installer] Files in current directory:
  dir /b
  if exist "%~dp0installers" (
    echo [installer] Files in installers directory:
    dir /b "%~dp0installers"
  )
  pause
  exit /b 1
)

for /f "delims=" %%I in ('where python.exe 2^>nul') do (
  set "PYTHON_CMD=%%I"
  goto python_found
)
for /f "delims=" %%I in ('where py.exe 2^>nul') do (
  set "PYTHON_CMD=%%I"
  goto python_found
)

if not defined PYTHON_CMD (
  echo [installer] ERROR: Python no esta disponible en este sistema.
  pause
  exit /b 1
)

:python_found
echo [installer] Using script: %SCRIPT%
echo [installer] Using Python: %PYTHON_CMD%
"%PYTHON_CMD%" "%SCRIPT%" --install

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
