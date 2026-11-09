@echo off
title KDM - Tro ly cai dat Extension Trinh Duyet
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================================
echo   KDM - Kevin Download Manager: Cài Đặt Extension
echo ========================================================
echo.
echo Dang mo trang quan ly tien ich tren cac trinh duyet...
start coccoc://extensions 2>nul
start chrome://extensions 2>nul
start edge://extensions 2>nul
echo.
echo Dang mo thu muc chua Extension KDM...
if exist "%~dp0kdm_extension" (
    explorer.exe "%~dp0kdm_extension"
) else (
    explorer.exe "%~dp0"
)
echo.
echo ========================================================
echo HUONG DAN (CHI MAT 3 GIAY):
echo 1. Tren trinh duyet (Coc Coc, Chrome, Edge), gat bat:
echo    "Che do danh cho nha phat trien" (Developer mode)
echo 2. Keo thu muc "kdm_extension" vua mo tha vao trinh duyet!
echo.
echo Xong! Extension KDM se duoc tich hop ngay lap tuc!
echo ========================================================
echo.
pause
