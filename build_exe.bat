@echo off
title Build KDM Standalone EXE
cd /d "%~dp0"
echo ========================================================
echo   Dong goi KDM (Kevin Download Manager) thanh file EXE
echo   (Chay doc lap khong can cai Python)
echo ========================================================
echo.

python -m PyInstaller --noconsole --name "KDM" --icon "kdm_icon.ico" --collect-all customtkinter --collect-all imageio_ffmpeg --add-data "kdm_extension;kdm_extension" --add-data "kdm_icon.ico;." kdm_app.py --clean

if exist "dist\KDM\KDM.exe" (
    echo.
    echo Dang sao chep Extension vao thu muc dist\KDM...
    xcopy /E /I /Y "kdm_extension" "dist\KDM\kdm_extension" >nul
    copy /Y "kdm_extension_firefox.zip" "dist\KDM\kdm_extension_firefox.zip" >nul
    echo ========================================================
    echo [OK] DA DONG GOI THANH CONG!
    echo Thu muc chua file EXE: dist\KDM\KDM.exe
    echo Ban co the chep nguyen thu muc "dist\KDM" sang bat ky
    echo may tinh Windows nao de chay ma KHONG CAN CAI PYTHON!
    echo ========================================================
) else (
    echo.
    echo [ERROR] Dong goi that bai. Vui long kiem tra loi phia tren.
)

pause
