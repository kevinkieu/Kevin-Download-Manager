@echo off
title Build KDM Setup Installer
cd /d "%~dp0"
echo ========================================================
echo   Dong goi file cai dat: KDM_Setup_v1.2.exe
echo   (Trinh cai dat chuyen nghiep voi Inno Setup)
echo ========================================================
echo.

set "ISCC_PATH=C:\Users\huank\AppData\Local\Programs\Inno Setup 6\ISCC.exe"

if not exist "%ISCC_PATH%" (
    echo [ERROR] Khong tim thay Inno Setup compiler tai: %ISCC_PATH%
    pause
    exit /b 1
)

if not exist "dist\KDM\KDM.exe" (
    echo [ERROR] Khong tim thay dist\KDM\KDM.exe! Vui long chay build_exe.bat truoc.
    pause
    exit /b 1
)

echo Dang sao chep cac file phu tro vao dist\KDM...
xcopy /E /I /Y "kdm_extension" "dist\KDM\kdm_extension" >nul
copy /Y "kdm_extension_firefox.zip" "dist\KDM\kdm_extension_firefox.zip" >nul
copy /Y "install_extension_helper.bat" "dist\KDM\install_extension_helper.bat" >nul
if not exist "dist\KDM\installer_assets" mkdir "dist\KDM\installer_assets"
copy /Y "installer_assets\welcome.html" "dist\KDM\installer_assets\welcome.html" >nul

echo Dang bien dich tap tin cai dat bang Inno Setup...
"%ISCC_PATH%" "installer.iss"

if exist "dist_installer\KDM_Setup_v1.2.exe" (
    echo.
    echo ========================================================
    echo [OK] DA DONG GOI FILE CAI DAT THANH CONG!
    echo File Setup: dist_installer\KDM_Setup_v1.2.exe
    echo Ban co the gui file nay cho ban be va gia dinh de cai dat!
    echo ========================================================
) else (
    echo.
    echo [ERROR] Bien dich file Setup that bai!
)

echo.
pause
