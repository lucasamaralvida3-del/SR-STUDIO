@echo off
setlocal EnableExtensions
title SR Studio
cd /d "%~dp0"

set "PYEXE="

for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
  if exist "%%~fD\python.exe" (
    "%%~fD\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
      set "PYEXE=%%~fD\python.exe"
      goto :FOUND
    )
  )
)

for /f "delims=" %%P in ('where python 2^>nul') do (
  echo %%P | find /I "\WindowsApps\" >nul
  if errorlevel 1 (
    "%%P" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
      set "PYEXE=%%P"
      goto :FOUND
    )
  )
)

where winget >nul 2>&1
if errorlevel 1 (
  echo Python real nao encontrado e WinGet indisponivel.
  pause
  exit /b 1
)

echo Instalando Python...
winget install --id Python.Python.3.13 -e --source winget --scope user --accept-package-agreements --accept-source-agreements

for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do (
  if exist "%%~fD\python.exe" (
    set "PYEXE=%%~fD\python.exe"
    goto :FOUND
  )
)

echo Reinicie o Windows e execute novamente.
pause
exit /b 1

:FOUND
echo Python: %PYEXE%
"%PYEXE%" -m pip install --upgrade pip
if errorlevel 1 goto :ERR
"%PYEXE%" -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 goto :ERR

"%PYEXE%" "%~dp0SR_Studio_Gerador.py"
if errorlevel 1 goto :ERR
exit /b 0

:ERR
echo.
echo O SR Studio encontrou um erro.
pause
exit /b 1
