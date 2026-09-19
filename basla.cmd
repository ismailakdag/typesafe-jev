@echo off
rem Sunucuyu PATH'ten bagimsiz baslatir: uv PATH'te yoksa bilinen kurulum yerine bakar.
rem Cift tiklayarak da calisir.
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "UV="
where uv >nul 2>&1 && set "UV=uv"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"

if not defined UV (
  echo.
  echo   uv bulunamadi.
  echo   Kurmak icin: powershell -c "irm https://astral.sh/uv/install.ps1 ^| iex"
  echo.
  pause
  exit /b 1
)

rem Port doluysa uvicorn'un yigin izi yerine anlasilir bir mesaj ver.
netstat -ano | findstr /r /c:"127.0.0.1:8765 .* LISTENING" >nul
if not errorlevel 1 (
  echo.
  echo   Sunucu ZATEN CALISIYOR:  http://127.0.0.1:8765
  echo   Tarayicida bu adresi acman yeterli, yeniden baslatmaya gerek yok.
  echo.
  echo   Yeniden baslatmak istersen once onu calistiran pencerede Ctrl+C yap,
  echo   ya da su komutla durdur:
  echo     powershell -c "Stop-Process -Id (Get-NetTCPConnection -LocalPort 8765 -State Listen).OwningProcess -Force"
  echo.
  pause
  exit /b 0
)

echo.
echo   Ilan Eleme  -  http://127.0.0.1:8765
echo   Tarayicida bu adresi ac. Durdurmak icin Ctrl+C.
echo.

"%UV%" run python -m server.app
