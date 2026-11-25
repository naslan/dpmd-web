@echo off
rem Menjalankan website DPMD di Windows (klik dua kali berkas ini)
cd /d "%~dp0"
if not exist venv (
    echo Membuat lingkungan Python...
    python -m venv venv
)
call venv\Scripts\activate
pip install -q -r requirements.txt
if "%ADMIN_PASSWORD%"=="" set /p ADMIN_PASSWORD=Masukkan kata sandi admin: 
set HOST=0.0.0.0
python serve.py
pause
