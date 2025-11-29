@echo off
echo ========================================
echo   REINICIAR SERVIDOR BACKEND
echo   Sistema de Cierre de Caja KOAJ
echo ========================================
echo.

REM Detener procesos existentes en puerto 5000
echo [1/3] Deteniendo servidor anterior...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000 ^| findstr LISTENING') do (
    echo Matando proceso %%a
    taskkill /PID %%a /F >nul 2>&1
)
echo.

REM Esperar un momento
timeout /t 2 /nobreak >nul

REM Verificar configuracion de CORS
echo [2/3] Verificando configuracion de CORS...
findstr "ALLOWED_ORIGINS" .env >nul
if %errorlevel% equ 0 (
    echo [OK] Archivo .env encontrado
    findstr "127.0.0.1:5173" .env >nul
    if %errorlevel% equ 0 (
        echo [OK] URL 127.0.0.1:5173 configurada
    ) else (
        echo [ADVERTENCIA] Falta URL 127.0.0.1:5173 en ALLOWED_ORIGINS
    )

    findstr "10.28.168.57:5173" .env >nul
    if %errorlevel% equ 0 (
        echo [OK] URL 10.28.168.57:5173 configurada
    ) else (
        echo [ADVERTENCIA] Falta URL 10.28.168.57:5173 en ALLOWED_ORIGINS
    )
) else (
    echo [ERROR] No se encontro configuracion de CORS en .env
    pause
    exit /b 1
)
echo.

REM Iniciar servidor
echo [3/3] Iniciando servidor...
echo.
echo ========================================
echo   SERVIDOR INICIANDO
echo ========================================
echo.
echo El servidor se esta iniciando...
echo Presiona Ctrl+C para detenerlo
echo.

python run.py

pause
