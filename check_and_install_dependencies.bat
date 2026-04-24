@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "REQ_FILE=%ROOT%Data\AIPresenter\Scripts\requirements-aipresenter.txt"
set "TOOLS_DIR=%ROOT%Data\AIPresenter\Tools"
set "LOCAL_FFMPEG=%TOOLS_DIR%\ffmpeg.exe"
set "LOCAL_FFPLAY=%TOOLS_DIR%\ffplay.exe"
set "LOCAL_FFPROBE=%TOOLS_DIR%\ffprobe.exe"
set "SETTINGS_FILE=%ROOT%Data\AIPresenter\Config\ai_settings.json"

set "HAS_FAILURE="
set "HAS_WINGET=0"
set "PY_CMD="
set "GLOBAL_FFMPEG="
set "GLOBAL_FFPLAY="
set "GLOBAL_FFPROBE="
set "CFG_FFMPEG="
set "CFG_FFPLAY="
set "CFG_FFPROBE="
set "DOWNLOADED_FFMPEG="
set "DOWNLOADED_FFPLAY="
set "DOWNLOADED_FFPROBE="
set "WINAPPS_DIR=%LocalAppData%\Microsoft\WindowsApps\"

set "WAIT_ON_EXIT=1"
if /I "%~1"=="--no-wait" set "WAIT_ON_EXIT=0"

echo ====================================================
echo NHOP Project dependency check and install
echo Root: %ROOT%
echo ====================================================
echo.

call :check_winget
call :ensure_python
call :ensure_pip
call :ensure_requirements
call :ensure_ffmpeg_local

echo.
set "FINAL_CODE=0"
if defined HAS_FAILURE (
  echo [WARN] Completed with issues. Please review the messages above.
  set "FINAL_CODE=1"
) else (
  echo [SUCCESS] All checks are complete. Everything is ready.
)
call :finish %FINAL_CODE%
exit /b %FINAL_CODE%

:finish
set "EXIT_CODE=%~1"
if "%WAIT_ON_EXIT%"=="1" (
  echo.
  set /p "DUMMY=Press Enter to close this window... "
)
exit /b %EXIT_CODE%

:check_winget
where winget >nul 2>nul
if errorlevel 1 (
  set "HAS_WINGET=0"
  echo [INFO] winget is not available. Fallback methods will be used when needed.
) else (
  set "HAS_WINGET=1"
  echo [OK] winget is available.
)
echo.
exit /b 0

:refresh_path
set "PATH=%PATH%;%LocalAppData%\Microsoft\WindowsApps;%ProgramFiles%\Python311;%ProgramFiles%\Python311\Scripts;%LocalAppData%\Programs\Python\Python311;%LocalAppData%\Programs\Python\Python311\Scripts;%ProgramFiles%\Python312;%ProgramFiles%\Python312\Scripts;%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts"
exit /b 0

:detect_python_cmd
set "PY_CMD="

for /f "delims=" %%P in ('where py 2^>nul') do (
  if /I not "%%~dpP"=="%WINAPPS_DIR%" (
    "%%~fP" -3 -m pip --version >nul 2>nul
    if not errorlevel 1 (
      set "PY_CMD=py -3"
      exit /b 0
    )
    "%%~fP" -m pip --version >nul 2>nul
    if not errorlevel 1 (
      set "PY_CMD=py"
      exit /b 0
    )
  )
)

for /f "delims=" %%P in ('where python 2^>nul') do (
  if /I not "%%~dpP"=="%WINAPPS_DIR%" (
    "%%~fP" -m pip --version >nul 2>nul
    if not errorlevel 1 (
      set "PY_CMD="%%~fP""
      exit /b 0
    )
  )
)

call :scan_python_dirs_with_pip "%LocalAppData%\Programs\Python"
if defined PY_CMD exit /b 0
call :scan_python_dirs_with_pip "%ProgramFiles%"
if defined PY_CMD exit /b 0
call :scan_python_dirs_with_pip "%ProgramFiles(x86)%"
if defined PY_CMD exit /b 0

rem Fallback: select a non-alias Python command even if pip is missing.
for /f "delims=" %%P in ('where py 2^>nul') do (
  if /I not "%%~dpP"=="%WINAPPS_DIR%" (
    set "PY_CMD=py -3"
    exit /b 0
  )
)

for /f "delims=" %%P in ('where python 2^>nul') do (
  if /I not "%%~dpP"=="%WINAPPS_DIR%" (
    set "PY_CMD="%%~fP""
    exit /b 0
  )
)

call :scan_python_dirs "%LocalAppData%\Programs\Python"
if defined PY_CMD exit /b 0
call :scan_python_dirs "%ProgramFiles%"
if defined PY_CMD exit /b 0
call :scan_python_dirs "%ProgramFiles(x86)%"
if defined PY_CMD exit /b 0

exit /b 0

:scan_python_dirs_with_pip
set "SCAN_ROOT=%~1"
if "%SCAN_ROOT%"=="" exit /b 0
if not exist "%SCAN_ROOT%" exit /b 0

for /d %%V in ("%SCAN_ROOT%\Python3*") do (
  if exist "%%~fV\python.exe" (
    "%%~fV\python.exe" -m pip --version >nul 2>nul
    if not errorlevel 1 (
      set "PY_CMD="%%~fV\python.exe""
      exit /b 0
    )
  )
)
exit /b 0

:scan_python_dirs
set "SCAN_ROOT=%~1"
if "%SCAN_ROOT%"=="" exit /b 0
if not exist "%SCAN_ROOT%" exit /b 0

for /d %%V in ("%SCAN_ROOT%\Python3*") do (
  if exist "%%~fV\python.exe" (
    set "PY_CMD="%%~fV\python.exe""
    exit /b 0
  )
)
exit /b 0

:validate_python_cmd
set "PY_VALID=0"
set "PY_EXE="
if not defined PY_CMD exit /b 0

for /f "usebackq delims=" %%E in (`%PY_CMD% -c "import sys; print(sys.executable)" 2^>nul`) do (
  set "PY_EXE=%%~fE"
  goto :validate_python_cmd_done
)

:validate_python_cmd_done
if not defined PY_EXE exit /b 0
echo !PY_EXE! | findstr /I /C:"\Microsoft\WindowsApps\" >nul
if not errorlevel 1 exit /b 0

set "PY_VALID=1"
exit /b 0

:ensure_python
call :refresh_path
call :detect_python_cmd
call :validate_python_cmd
if "!PY_VALID!"=="1" (
  echo [OK] Python is already available via !PY_CMD!. No download is needed.
  echo.
  exit /b 0
)
set "PY_CMD="

echo [MISSING] Python is not found.

if "%HAS_WINGET%"=="1" (
  echo [ACTION] Installing Python 3.11 with winget...
  winget install --id Python.Python.3.11 -e --accept-package-agreements --accept-source-agreements
  call :refresh_path
  call :detect_python_cmd
  call :validate_python_cmd
  if "!PY_VALID!"=="1" (
    echo [OK] Python installed successfully via winget. Using !PY_CMD!.
    echo.
    exit /b 0
  )
)

echo [ACTION] Trying fallback installer from python.org...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $url='https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe'; $dst=Join-Path $env:TEMP 'python-3.11.9-amd64.exe'; Invoke-WebRequest -Uri $url -OutFile $dst; Start-Process -FilePath $dst -ArgumentList '/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_pip=1' -Wait"
if errorlevel 1 (
  echo [ERROR] PowerShell command to download Python installer failed.
  set "HAS_FAILURE=1"
  echo.
  exit /b 0
)

call :refresh_path
call :detect_python_cmd
call :validate_python_cmd
if "!PY_VALID!"=="1" (
  echo [OK] Python installed successfully via fallback installer. Using !PY_CMD!.
) else (
  echo [ERROR] Could not install Python automatically.
  set "HAS_FAILURE=1"
)
echo.
exit /b 0

:ensure_pip
if not defined PY_CMD call :detect_python_cmd
call :validate_python_cmd
if not "!PY_VALID!"=="1" set "PY_CMD="
if not defined PY_CMD (
  echo [SKIP] pip check skipped because a valid Python interpreter is not available.
  set "HAS_FAILURE=1"
  echo.
  exit /b 0
)

%PY_CMD% -m pip --version >nul 2>nul
if not errorlevel 1 (
  echo [OK] pip is already available. No download is needed.
  echo.
  exit /b 0
)

echo [MISSING] pip is not available for %PY_CMD%.
echo [ACTION] Running ensurepip...
%PY_CMD% -m ensurepip --upgrade >nul 2>nul
call :refresh_path
%PY_CMD% -m pip --version >nul 2>nul
if not errorlevel 1 (
  echo [OK] pip was installed successfully.
  echo.
  exit /b 0
)

echo [ACTION] Trying get-pip.py fallback...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $dst=Join-Path $env:TEMP 'get-pip.py'; Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile $dst"
if errorlevel 1 (
  echo [ERROR] PowerShell command to download get-pip.py failed.
  set "HAS_FAILURE=1"
  echo.
  exit /b 0
)

if not exist "%TEMP%\get-pip.py" (
  echo [ERROR] get-pip.py was not downloaded.
  set "HAS_FAILURE=1"
  echo.
  exit /b 0
)

%PY_CMD% "%TEMP%\get-pip.py" >nul 2>nul
if errorlevel 1 (
  echo [WARN] get-pip.py returned a non-zero exit code. Re-checking pip...
)

call :refresh_path
%PY_CMD% -m pip --version >nul 2>nul
if not errorlevel 1 (
  echo [OK] pip was installed successfully via fallback.
) else (
  echo [ERROR] pip installation failed.
  set "HAS_FAILURE=1"
)
echo.
exit /b 0

:ensure_requirements
if not exist "%REQ_FILE%" (
  echo [SKIP] Requirements file not found: %REQ_FILE%
  echo.
  exit /b 0
)

if not defined PY_CMD call :detect_python_cmd
call :validate_python_cmd
if not "!PY_VALID!"=="1" set "PY_CMD="
if not defined PY_CMD (
  echo [SKIP] Python package check skipped because a valid Python interpreter is not available.
  set "HAS_FAILURE=1"
  echo.
  exit /b 0
)

%PY_CMD% -m pip --version >nul 2>nul
if errorlevel 1 (
  echo [ERROR] pip is still unavailable for %PY_CMD%.
  set "HAS_FAILURE=1"
  echo.
  exit /b 0
)

echo [ACTION] Verifying and installing Python packages from requirements file...
set "PIP_LOG=%TEMP%\nhop_pip_requirements.log"
if exist "%PIP_LOG%" del /f /q "%PIP_LOG%" >nul 2>nul

%PY_CMD% -m pip install --disable-pip-version-check --quiet --upgrade pip >"%PIP_LOG%" 2>&1
if errorlevel 1 (
  echo [WARN] pip upgrade returned a non-zero exit code. Continuing with requirements install...
)

%PY_CMD% -m pip install --disable-pip-version-check --quiet -r "%REQ_FILE%" >>"%PIP_LOG%" 2>&1
if errorlevel 1 (
  echo [ERROR] Python package installation failed.
  echo [INFO] pip details:
  type "%PIP_LOG%"
  set "HAS_FAILURE=1"
  echo.
  exit /b 0
)

call :refresh_path
if exist "%PIP_LOG%" del /f /q "%PIP_LOG%" >nul 2>nul

%PY_CMD% -c "import pptx" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python-pptx is still not importable in the selected Python interpreter.
  set "HAS_FAILURE=1"
  echo.
  exit /b 0
)

%PY_CMD% -c "import openpyxl" >nul 2>nul
if errorlevel 1 (
  echo [WARN] openpyxl is not importable after requirements install. Trying direct install...
  %PY_CMD% -m pip install --disable-pip-version-check --quiet "openpyxl>=3.1.5" >>"%PIP_LOG%" 2>&1
  if errorlevel 1 (
    echo [ERROR] openpyxl direct install failed.
    echo [INFO] pip details:
    type "%PIP_LOG%"
    set "HAS_FAILURE=1"
    echo.
    exit /b 0
  )

  %PY_CMD% -c "import openpyxl" >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] openpyxl is still not importable in the selected Python interpreter.
    set "HAS_FAILURE=1"
    echo.
    exit /b 0
  )
)

%PY_CMD% -c "from PIL import Image" >nul 2>nul
if errorlevel 1 (
  echo [WARN] Pillow is not importable after requirements install. Trying direct install...
  %PY_CMD% -m pip install --disable-pip-version-check --quiet "Pillow>=10.0.0" >>"%PIP_LOG%" 2>&1
  if errorlevel 1 (
    echo [ERROR] Pillow direct install failed.
    echo [INFO] pip details:
    type "%PIP_LOG%"
    set "HAS_FAILURE=1"
    echo.
    exit /b 0
  )

  %PY_CMD% -c "from PIL import Image" >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Pillow is still not importable in the selected Python interpreter.
    set "HAS_FAILURE=1"
    echo.
    exit /b 0
  )
)

%PY_CMD% -c "import comtypes" >nul 2>nul
if errorlevel 1 (
  echo [WARN] comtypes is not importable after requirements install. Trying direct install...
  %PY_CMD% -m pip install --disable-pip-version-check --quiet "comtypes>=1.2.0" >>"%PIP_LOG%" 2>&1
  if errorlevel 1 (
    echo [ERROR] comtypes direct install failed.
    echo [INFO] pip details:
    type "%PIP_LOG%"
    set "HAS_FAILURE=1"
    echo.
    exit /b 0
  )

  %PY_CMD% -c "import comtypes" >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] comtypes is still not importable in the selected Python interpreter.
    set "HAS_FAILURE=1"
    echo.
    exit /b 0
  )
)

%PY_CMD% -c "import win32com.client" >nul 2>nul
if errorlevel 1 (
  echo [WARN] pywin32 (win32com) is not importable after requirements install. Trying direct install...
  %PY_CMD% -m pip install --disable-pip-version-check --quiet "pywin32>=306" >>"%PIP_LOG%" 2>&1
  if errorlevel 1 (
    echo [ERROR] pywin32 direct install failed.
    echo [INFO] pip details:
    type "%PIP_LOG%"
    set "HAS_FAILURE=1"
    echo.
    exit /b 0
  )

  %PY_CMD% -m pywin32_postinstall -install >nul 2>nul

  %PY_CMD% -c "import win32com.client" >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] pywin32 (win32com) is still not importable in the selected Python interpreter.
    set "HAS_FAILURE=1"
    echo.
    exit /b 0
  )
)

%PY_CMD% -c "import tkinter" >nul 2>nul
if errorlevel 1 (
  echo [ERROR] tkinter is not available in the selected Python interpreter.
  echo [INFO] tkinter is part of standard Python on Windows and is not reliably installed via pip.
  echo [ACTION] Reinstall Python and enable "tcl/tk and IDLE", then rerun this script.
  set "HAS_FAILURE=1"
  echo.
  exit /b 0
)

set "PPTX_VER="
for /f "usebackq delims=" %%V in (`%PY_CMD% -c "import pptx; print(pptx.__version__)" 2^>nul`) do (
  set "PPTX_VER=%%V"
)
if not defined PPTX_VER set "PPTX_VER=unknown"

set "OPENPYXL_VER="
for /f "usebackq delims=" %%V in (`%PY_CMD% -c "import openpyxl; print(openpyxl.__version__)" 2^>nul`) do (
  set "OPENPYXL_VER=%%V"
)
if not defined OPENPYXL_VER set "OPENPYXL_VER=unknown"

set "PILLOW_VER="
for /f "usebackq delims=" %%V in (`%PY_CMD% -c "import PIL; print(PIL.__version__)" 2^>nul`) do (
  set "PILLOW_VER=%%V"
)
if not defined PILLOW_VER set "PILLOW_VER=unknown"

set "COMTYPES_VER="
for /f "usebackq delims=" %%V in (`%PY_CMD% -c "import comtypes; print(getattr(comtypes, '__version__', 'unknown'))" 2^>nul`) do (
  set "COMTYPES_VER=%%V"
)
if not defined COMTYPES_VER set "COMTYPES_VER=unknown"

set "PYWIN32_VER="
for /f "usebackq delims=" %%V in (`%PY_CMD% -c "import importlib.metadata as m; print(m.version('pywin32'))" 2^>nul`) do (
  set "PYWIN32_VER=%%V"
)
if not defined PYWIN32_VER set "PYWIN32_VER=unknown"

set "TK_VER="
for /f "usebackq delims=" %%V in (`%PY_CMD% -c "import tkinter as tk; print(tk.TkVersion)" 2^>nul`) do (
  set "TK_VER=%%V"
)
if not defined TK_VER set "TK_VER=unknown"

echo [OK] Python requirements are satisfied.
echo [OK] python-pptx import check passed (version !PPTX_VER!).
echo [OK] openpyxl import check passed (version !OPENPYXL_VER!).
echo [OK] Pillow import check passed (version !PILLOW_VER!).
echo [OK] comtypes import check passed (version !COMTYPES_VER!).
echo [OK] pywin32 import check passed (version !PYWIN32_VER!).
echo [OK] tkinter import check passed (Tk !TK_VER!).
echo.
exit /b 0

:ensure_ffmpeg_local
if not exist "%TOOLS_DIR%" mkdir "%TOOLS_DIR%" >nul 2>nul

if exist "%LOCAL_FFMPEG%" if exist "%LOCAL_FFPLAY%" if exist "%LOCAL_FFPROBE%" (
  echo [OK] Local ffmpeg.exe, ffplay.exe and ffprobe.exe are already present in Data\AIPresenter\Tools. No download is needed.
  echo.
  exit /b 0
)

echo [MISSING] Local ffmpeg, ffplay and ffprobe are not complete in Data\AIPresenter\Tools.

call :find_global_ffmpeg
if defined GLOBAL_FFMPEG if defined GLOBAL_FFPLAY if defined GLOBAL_FFPROBE (
  call :try_place_ffmpeg_bundle "%GLOBAL_FFMPEG%" "%GLOBAL_FFPLAY%" "%GLOBAL_FFPROBE%" "system PATH"
)

if exist "%LOCAL_FFMPEG%" if exist "%LOCAL_FFPLAY%" if exist "%LOCAL_FFPROBE%" (
  echo [OK] Local ffmpeg.exe, ffplay.exe and ffprobe.exe are ready.
  echo.
  exit /b 0
)

call :find_ffmpeg_from_settings
if defined CFG_FFMPEG if defined CFG_FFPLAY if defined CFG_FFPROBE (
  call :try_place_ffmpeg_bundle "%CFG_FFMPEG%" "%CFG_FFPLAY%" "%CFG_FFPROBE%" "ai_settings.json"
)

if exist "%LOCAL_FFMPEG%" if exist "%LOCAL_FFPLAY%" if exist "%LOCAL_FFPROBE%" (
  echo [OK] Local ffmpeg.exe, ffplay.exe and ffprobe.exe are ready.
  echo.
  exit /b 0
)

call :find_user_downloaded_ffmpeg
if defined DOWNLOADED_FFMPEG if defined DOWNLOADED_FFPLAY if defined DOWNLOADED_FFPROBE (
  call :try_place_ffmpeg_bundle "%DOWNLOADED_FFMPEG%" "%DOWNLOADED_FFPLAY%" "%DOWNLOADED_FFPROBE%" "downloaded folders"
)

if exist "%LOCAL_FFMPEG%" if exist "%LOCAL_FFPLAY%" if exist "%LOCAL_FFPROBE%" (
  echo [OK] Local ffmpeg.exe, ffplay.exe and ffprobe.exe are ready.
  echo.
  exit /b 0
)

if "%HAS_WINGET%"=="1" (
  echo [ACTION] Installing FFmpeg with winget...
  winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
  call :refresh_path
  call :find_global_ffmpeg
  if defined GLOBAL_FFMPEG if defined GLOBAL_FFPLAY if defined GLOBAL_FFPROBE (
    call :try_place_ffmpeg_bundle "%GLOBAL_FFMPEG%" "%GLOBAL_FFPLAY%" "%GLOBAL_FFPROBE%" "winget installation"
  )
)

if exist "%LOCAL_FFMPEG%" if exist "%LOCAL_FFPLAY%" if exist "%LOCAL_FFPROBE%" (
  echo [OK] Local ffmpeg.exe, ffplay.exe and ffprobe.exe are ready.
  echo.
  exit /b 0
)

echo [ACTION] Trying FFmpeg zip fallback download...
call :download_ffmpeg_fallback
if exist "%LOCAL_FFMPEG%" if exist "%LOCAL_FFPLAY%" if exist "%LOCAL_FFPROBE%" (
  echo [OK] Local ffmpeg.exe, ffplay.exe and ffprobe.exe are ready.
) else (
  echo [ERROR] Could not prepare local ffmpeg, ffplay and ffprobe automatically.
  echo [INFO] Please install FFmpeg manually and put ffmpeg.exe, ffplay.exe and ffprobe.exe into Data\AIPresenter\Tools.
  set "HAS_FAILURE=1"
)
echo.
exit /b 0

:try_place_ffmpeg_bundle
set "SRC_FFMPEG=%~1"
set "SRC_FFPLAY=%~2"
set "SRC_FFPROBE=%~3"
set "SRC_LABEL=%~4"

if "%SRC_FFMPEG%"=="" exit /b 1
if "%SRC_FFPLAY%"=="" exit /b 1
if "%SRC_FFPROBE%"=="" exit /b 1
if not exist "%SRC_FFMPEG%" exit /b 1
if not exist "%SRC_FFPLAY%" exit /b 1
if not exist "%SRC_FFPROBE%" exit /b 1

if /I "%SRC_FFMPEG%"=="%LOCAL_FFMPEG%" if /I "%SRC_FFPLAY%"=="%LOCAL_FFPLAY%" if /I "%SRC_FFPROBE%"=="%LOCAL_FFPROBE%" exit /b 0

echo [ACTION] Copying ffmpeg, ffplay and ffprobe from %SRC_LABEL% to Data\AIPresenter\Tools...

if /I not "%SRC_FFMPEG%"=="%LOCAL_FFMPEG%" (
  copy /Y "%SRC_FFMPEG%" "%LOCAL_FFMPEG%" >nul 2>nul
)

if /I not "%SRC_FFPLAY%"=="%LOCAL_FFPLAY%" (
  copy /Y "%SRC_FFPLAY%" "%LOCAL_FFPLAY%" >nul 2>nul
)

if /I not "%SRC_FFPROBE%"=="%LOCAL_FFPROBE%" (
  copy /Y "%SRC_FFPROBE%" "%LOCAL_FFPROBE%" >nul 2>nul
)

if exist "%LOCAL_FFMPEG%" if exist "%LOCAL_FFPLAY%" if exist "%LOCAL_FFPROBE%" (
  echo [OK] ffmpeg, ffplay and ffprobe are now ready in Data\AIPresenter\Tools.
  exit /b 0
)

echo [WARN] Could not place ffmpeg, ffplay and ffprobe from %SRC_LABEL%. Continuing with next method.
exit /b 1

:find_ffmpeg_from_settings
set "CFG_FFMPEG="
set "CFG_FFPLAY="
set "CFG_FFPROBE="

if not exist "%SETTINGS_FILE%" exit /b 0

for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $p='%SETTINGS_FILE%'; if(Test-Path $p){ try { $j=Get-Content -Raw -Path $p | ConvertFrom-Json; $raw=[string]$j.ffmpeg_path; if($raw){ if([System.IO.Path]::IsPathRooted($raw)){ $ff=$raw } else { $ff=Join-Path '%ROOT%' $raw }; if(Test-Path $ff){ $ff=(Resolve-Path $ff).Path; $dir=Split-Path $ff -Parent; $fp=Join-Path $dir 'ffplay.exe'; $fr=Join-Path $dir 'ffprobe.exe'; if((Test-Path $fp) -and (Test-Path $fr)){ $ff; (Resolve-Path $fp).Path; (Resolve-Path $fr).Path } } } } catch {} }"`) do (
  if not defined CFG_FFMPEG (
    set "CFG_FFMPEG=%%~A"
  ) else if not defined CFG_FFPLAY (
    set "CFG_FFPLAY=%%~A"
  ) else if not defined CFG_FFPROBE (
    set "CFG_FFPROBE=%%~A"
  )
)

if defined CFG_FFMPEG if defined CFG_FFPLAY if defined CFG_FFPROBE echo [INFO] Found ffmpeg, ffplay and ffprobe from ai_settings.json path.
exit /b 0

:find_user_downloaded_ffmpeg
set "DOWNLOADED_FFMPEG="
set "DOWNLOADED_FFPLAY="
set "DOWNLOADED_FFPROBE="

for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $candidates=@(); $u=$env:USERPROFILE; if($u){ $candidates += (Join-Path $u 'Downloads'); $candidates += (Join-Path $u 'Desktop'); $candidates += (Join-Path $u 'Documents') }; if($env:OneDrive){ $candidates += (Join-Path $env:OneDrive 'Downloads'); $candidates += (Join-Path $env:OneDrive 'Desktop'); $candidates += (Join-Path $env:OneDrive 'Documents') }; Get-PSDrive -PSProvider FileSystem | ForEach-Object { foreach($n in @('ffmpeg','tools','Downloads')){ $p=Join-Path $_.Root $n; $candidates += $p } }; $roots=$candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique; $pairs=@(); foreach($r in $roots){ Get-ChildItem -Path $r -Recurse -Filter ffmpeg.exe -File -ErrorAction SilentlyContinue | ForEach-Object { $play=Join-Path $_.DirectoryName 'ffplay.exe'; $probe=Join-Path $_.DirectoryName 'ffprobe.exe'; if((Test-Path $play) -and (Test-Path $probe)){ $pairs += [pscustomobject]@{ffmpeg=$_.FullName; ffplay=$play; ffprobe=$probe; t=$_.LastWriteTimeUtc} } } }; if($pairs.Count -gt 0){ $best=$pairs | Sort-Object t -Descending | Select-Object -First 1; $best.ffmpeg; $best.ffplay; $best.ffprobe }"`) do (
  if not defined DOWNLOADED_FFMPEG (
    set "DOWNLOADED_FFMPEG=%%~A"
  ) else if not defined DOWNLOADED_FFPLAY (
    set "DOWNLOADED_FFPLAY=%%~A"
  ) else if not defined DOWNLOADED_FFPROBE (
    set "DOWNLOADED_FFPROBE=%%~A"
  )
)

if defined DOWNLOADED_FFMPEG if defined DOWNLOADED_FFPLAY if defined DOWNLOADED_FFPROBE echo [INFO] Found ffmpeg, ffplay and ffprobe from downloaded folders.
exit /b 0

:download_ffmpeg_fallback
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $zip=Join-Path $env:TEMP 'ffmpeg-release-essentials.zip'; $dst=Join-Path $env:TEMP 'ffmpeg-release-essentials'; if(Test-Path $zip){Remove-Item $zip -Force}; if(Test-Path $dst){Remove-Item $dst -Recurse -Force}; Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $zip; Expand-Archive -Path $zip -DestinationPath $dst -Force; $ffmpeg=Get-ChildItem -Path $dst -Recurse -Filter ffmpeg.exe | Select-Object -First 1; $ffplay=Get-ChildItem -Path $dst -Recurse -Filter ffplay.exe | Select-Object -First 1; $ffprobe=Get-ChildItem -Path $dst -Recurse -Filter ffprobe.exe | Select-Object -First 1; if(-not $ffmpeg -or -not $ffplay -or -not $ffprobe){ throw 'FFmpeg binaries not found in archive.' }; Copy-Item $ffmpeg.FullName -Destination '%LOCAL_FFMPEG%' -Force; Copy-Item $ffplay.FullName -Destination '%LOCAL_FFPLAY%' -Force; Copy-Item $ffprobe.FullName -Destination '%LOCAL_FFPROBE%' -Force"
if errorlevel 1 (
  echo [WARN] FFmpeg zip fallback download failed.
)
exit /b 0

:find_global_ffmpeg
set "GLOBAL_FFMPEG="
set "GLOBAL_FFPLAY="
set "GLOBAL_FFPROBE="
for /f "delims=" %%I in ('where ffmpeg 2^>nul') do (
  set "GLOBAL_FFMPEG=%%~fI"
  goto :found_ffmpeg
)
:found_ffmpeg
for /f "delims=" %%I in ('where ffplay 2^>nul') do (
  set "GLOBAL_FFPLAY=%%~fI"
  goto :found_ffplay
)
:found_ffplay
for /f "delims=" %%I in ('where ffprobe 2^>nul') do (
  set "GLOBAL_FFPROBE=%%~fI"
  goto :found_ffprobe
)
:found_ffprobe
exit /b 0
