@echo off
chcp 65001 > nul
if not exist .venv (
    py -3.9 -m venv .venv
)
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
pause
