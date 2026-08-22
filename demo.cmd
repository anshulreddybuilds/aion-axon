@echo off
REM Short launcher, so the command on camera is "demo" and nothing else.
REM
REM The reviewed recording opened with this on screen for its full 34
REM seconds, wrapped across two lines:
REM
REM   PS> C:\Users\sneha\Desktop\AION-AXON\.venv\Scripts\python.exe C:\Use
REM   rs\sneha\Desktop\AION-AXON-core\scripts\camera_test.py
REM
REM Three separate faults in one line: it wraps (which reads as a bug), it
REM never scrolls away, and it publishes the operator's real name to a
REM public YouTube video. Typing "demo" fixes all three at once, which is
REM cheaper than editing every take.
REM
REM Usage, from the repo root:
REM     demo            camera test, no Gemini quota
REM     demo golden     the full golden-path rehearsal

setlocal

set "REPO=%~dp0"
set "PY=%REPO%..\AION-AXON\.venv\Scripts\python.exe"

if not exist "%PY%" set "PY=%REPO%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

if /I "%~1"=="golden" (
    "%PY%" "%REPO%scripts\golden_path.py"
) else (
    "%PY%" "%REPO%scripts\camera_test.py"
)

endlocal
