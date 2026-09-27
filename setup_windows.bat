@echo off
setlocal
REM One-time setup, Windows. Run this from Anaconda Prompt:
REM     cd "the folder this file is in"
REM     setup_windows.bat
REM It builds both conda environments and downloads the aligner's English models. 30-45 minutes, mostly waiting.

echo(
echo ============================================================
echo   Conversation pipeline - one-time setup
echo ============================================================
echo(

where conda >nul 2>&1
if errorlevel 1 (
  echo I cannot find conda, so I cannot set anything up.
  echo(
  echo You are probably in the wrong window. Open "Anaconda Prompt" from the
  echo Start menu - NOT Command Prompt or PowerShell - then run:
  echo(
  echo     cd "%~dp0"
  echo     setup_windows.bat
  echo(
  echo If there is no Anaconda Prompt in the Start menu, install Miniconda first:
  echo     https://docs.conda.io/en/latest/miniconda.html
  echo(
  pause
  exit /b 1
)

echo [1 of 3] Building the transcription environment.
echo          Several gigabytes. Leave it alone; it is not stuck.
echo(
call conda env create -f "%~dp0environment_whisper.yml"
if errorlevel 1 (
  echo(
  echo   "whisper" already exists - updating it instead.
  call conda env update -f "%~dp0environment_whisper.yml" --prune
)

echo(
echo [2 of 3] Building the aligner environment.
echo(
call conda env create -f "%~dp0environment_mfa.yml"
if errorlevel 1 (
  echo(
  echo   "mfa2" already exists - updating it instead.
  call conda env update -f "%~dp0environment_mfa.yml" --prune
)

echo(
echo [3 of 3] Downloading the aligner's English models.
echo(
call conda run -n mfa2 --no-capture-output mfa model download acoustic english_us_arpa
call conda run -n mfa2 --no-capture-output mfa model download dictionary english_us_arpa
call conda run -n mfa2 --no-capture-output mfa model download g2p english_us_arpa

echo(
echo ============================================================
echo   Checking it all worked
echo ============================================================
call conda run -n whisper --no-capture-output python "%~dp0check_setup.py"

echo(
echo If the check above says "Ready", you are done. To transcribe a recording:
echo(
echo     conda activate whisper
echo     cd "%~dp0"
echo     python run_all.py
echo(
pause
