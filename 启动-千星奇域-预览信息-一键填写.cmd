@echo off
chcp 65001 >nul
rem Qianxing Qiyu - preview autofill launcher
rem Double-click this file. The Python app asks for admin (UAC) by itself.
setlocal
cd /d "%~dp0"

set "PYTHONDONTWRITEBYTECODE=1"
set "PYAPP=%~dp0千星奇域-预览信息-一键填写.py"

if not exist "%PYAPP%" goto nopy

where pyw >nul 2>&1
if %errorlevel%==0 goto runpyw

where pythonw >nul 2>&1
if %errorlevel%==0 goto runpythonw

where py >nul 2>&1
if %errorlevel%==0 goto runpy

where python >nul 2>&1
if %errorlevel%==0 goto runpython

if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" goto bundled
goto nopython

:bundled
start "" "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" "%PYAPP%"
goto done

:runpyw
start "" pyw -3 "%PYAPP%"
goto done

:runpythonw
start "" pythonw "%PYAPP%"
goto done

:runpy
start "" py -3 "%PYAPP%"
goto done

:runpython
start "" python "%PYAPP%"
goto done

:nopython
echo [ERROR] Python 3 not found. Install Python 3 with tkinter. No pip packages are required.
pause
goto done

:nopy
echo [ERROR] Tool script not found. Keep the launcher next to the tool script.
pause

:done
endlocal
