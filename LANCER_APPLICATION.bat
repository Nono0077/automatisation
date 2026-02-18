@echo off
title Generateur de Livres Enfants

echo.
echo  ==========================================
echo    Generateur de Livres Enfants Personnalises
echo  ==========================================
echo.
echo  Demarrage en cours...
echo  Le navigateur va s'ouvrir sur : http://localhost:8501
echo.
echo  Pour arreter l'application : fermez cette fenetre.
echo.

cd /d "%~dp0"
python -m streamlit run app.py --server.headless false --browser.gatherUsageStats false --server.port 8501

pause
