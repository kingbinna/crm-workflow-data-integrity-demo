@echo off
cd /d "%~dp0"
py -3 start_demo.py
if errorlevel 1 echo Ask a grown-up to check that Python 3 is installed from https://www.python.org/downloads/.
pause
