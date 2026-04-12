@echo off
setlocal EnableDelayedExpansion
REM Args: python_exe script_path --root root_dir exitcode_out_path
"%~1" "%~2" --root "%~3"
set "EC=!ERRORLEVEL!"
> "%~4" echo !EC!
exit /b !EC!
