@echo off
rem Double-click to open Rain Mixer Studio
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 (python rainmix.py studio) else (py rainmix.py studio)
if errorlevel 1 pause
