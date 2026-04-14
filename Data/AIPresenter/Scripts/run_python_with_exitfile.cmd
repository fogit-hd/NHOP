@echo off
setlocal EnableDelayedExpansion
REM Args: python_exe script_path --root root_dir exitcode_out_path

set "PY_EXE=%~1"
set "USE_PY_LAUNCHER=0"

if /I "%PY_EXE%"=="pythonw.exe" set "USE_PY_LAUNCHER=1"
if /I "%PY_EXE%"=="python.exe" set "USE_PY_LAUNCHER=1"
if /I "%PY_EXE%"=="pyw" set "USE_PY_LAUNCHER=1"
if /I "%PY_EXE%"=="py" set "USE_PY_LAUNCHER=1"

if "%USE_PY_LAUNCHER%"=="1" (
	where py >nul 2>nul
	if not errorlevel 1 (
		py -3 "%~2" --root "%~3"
	) else (
		"%~1" "%~2" --root "%~3"
	)
) else (
	"%~1" "%~2" --root "%~3"
)

set "EC=!ERRORLEVEL!"
> "%~4" echo !EC!
exit /b !EC!
