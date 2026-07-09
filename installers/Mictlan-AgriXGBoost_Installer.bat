@echo off
set SCRIPT=%~dp0desktop_installer.py
if not exist "%SCRIPT%" set SCRIPT=%~dp0installers\desktop_installer.py
where python >nul 2>nul
if %ERRORLEVEL%==0 (
  start "" python "%SCRIPT%" --install
  exit /b
)
where pythonw >nul 2>nul
if %ERRORLEVEL%==0 (
  start "" pythonw "%SCRIPT%" --install
  exit /b
)
echo Python no esta disponible en este sistema.
pause
