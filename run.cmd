@echo off
setlocal

set TTF=source/TiroTelugu-Regular.input.ttf
set UFO=source/TiroTelugu-Regular.ufo

echo.
echo === Colorize ===
python tools/colorize.py %TTF% --ufo %UFO%
if errorlevel 1 goto :error

echo.
echo === Generate test page ===
python tools/fonttest.py output/TiroTelugu-Regular.input-Colorized.ttf
if errorlevel 1 goto :error

echo.
echo === Done ===
goto :eof

:error
echo.
echo ERROR: Step failed with exit code %errorlevel%
exit /b %errorlevel%
