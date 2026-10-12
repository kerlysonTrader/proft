@echo off
rem Scanner do MT5 (SOMENTE LEITURA): le os precos do MT5 aberto e envia ao painel a cada 15 min.
rem Duplo clique para ligar; feche a janela (ou Ctrl+C) para parar. Precisa do MT5 da Doo aberto e logado.
title Scanner MT5 - painel (somente leitura)
cd /d "%~dp0.."
set PYTHONIOENCODING=utf-8
.venv\Scripts\python.exe -m bot.tools.run_mt5_scanner --send --loop 15
pause
