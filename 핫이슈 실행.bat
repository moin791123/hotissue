@echo off
chcp 65001 >nul
title 지금 이슈
cd /d "%~dp0"
rem 이미 백그라운드로 켜져 있으면 브라우저만 열고 끝난다. 아니면 이 창에서 서버가 돈다.
python server.py --open
if errorlevel 1 pause
