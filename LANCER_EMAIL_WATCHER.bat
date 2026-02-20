@echo off
chcp 65001 >nul
title Email Watcher - Generateur de livres
cd /d "%~dp0"
echo ========================================
echo  Email Watcher - Generateur de livres
echo ========================================
echo.
echo Surveillance de Gmail pour les commandes...
echo (Appuyez sur Ctrl+C pour arreter)
echo.
python email_watcher.py
pause
