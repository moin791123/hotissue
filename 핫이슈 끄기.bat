@echo off
chcp 65001 >nul
title 지금 이슈 끄기
cd /d "%~dp0"
python server.py --stop
timeout /t 3 >nul
