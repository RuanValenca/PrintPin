@echo off
echo Instalando dependencias...
python -m pip install --upgrade pyside6 pyinstaller
echo Gerando executavel...
REM Para trocar o icone do .exe, substitua o arquivo icon.ico (mesmo nome).
python -m PyInstaller --onefile --noconsole --name PrintPin --icon icon.ico --add-data "icon.ico;." printpin.py
echo.
echo Pronto! Seu executavel esta em: dist\PrintPin.exe
pause
