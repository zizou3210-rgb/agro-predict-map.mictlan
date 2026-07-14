@echo off
setlocal
cd /d "%~dp0"

set "SCRIPT="
set "PYTHON_CMD="
set "CANDIDATE1=%~dp0desktop_installer.py"
set "CANDIDATE2=%~dp0installers\desktop_installer.py"
set "BUNDLED_PY1=%~dp0python-runtime\python.exe"
set "BUNDLED_PY2=%~dp0runtime\windows\python-runtime\python.exe"

if exist "%CANDIDATE1%" set "SCRIPT=%CANDIDATE1%"
if not defined SCRIPT if exist "%CANDIDATE2%" set "SCRIPT=%CANDIDATE2%"

set "LOGDIR=%LOCALAPPDATA%\Mictlan-AgriXGBoost"
set "LOGFILE=%LOGDIR%\installer-output.log"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>nul

echo [installer] Working directory: %CD%
echo [installer] Candidate 1: %CANDIDATE1%
echo [installer] Candidate 2: %CANDIDATE2%
echo [installer] Bundled Python 1: %BUNDLED_PY1%
echo [installer] Bundled Python 2: %BUNDLED_PY2%
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

if exist "%BUNDLED_PY1%" set "PYTHON_CMD=%BUNDLED_PY1%"
if not defined PYTHON_CMD if exist "%BUNDLED_PY2%" set "PYTHON_CMD=%BUNDLED_PY2%"

if not defined PYTHON_CMD (
  for /f "delims=" %%I in ('where python.exe 2^>nul') do (
    echo %%I | findstr /i /c:"\WindowsApps\" >nul
    if errorlevel 1 (
      set "PYTHON_CMD=%%I"
      goto python_found
    )
  )
  for /f "delims=" %%I in ('where py.exe 2^>nul') do (
    set "PYTHON_CMD=%%I"
    goto python_found
  )
) else (
  goto python_found
)

if not defined PYTHON_CMD (
  echo [installer] ERROR: No bundled Python was found and no usable system Python is available.
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
