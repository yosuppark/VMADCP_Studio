@echo off
REM ========================================================
REM VM-ADCP Post-Processing Studio Launcher (Standalone EXE)
REM Works without Python installed on this PC!
REM ========================================================

cd /d "%~dp0"

if exist "dist\VMADCP_Studio\VMADCP_Studio.exe" (
    start "" "dist\VMADCP_Studio\VMADCP_Studio.exe" %*
) else (
    echo [ERROR] Cannot find dist\VMADCP_Studio\VMADCP_Studio.exe
    pause
)
