@echo off
setlocal

set TTF=source/TiroTelugu-Regular.input.ttf
set UFO=source/TiroTelugu-Regular.ufo

echo === Colorize ===
python tools/colorize.py %TTF% --ufo %UFO% -o output/TiroSundaraTelugu-Regular.ttf -v
if errorlevel 1 goto :error

echo.
echo === Generate test page ===
python tools/fonttest.py output/TiroSundaraTelugu-Regular.ttf
if errorlevel 1 goto :error

echo.
echo === Done ===
goto :eof

:error
echo.
echo ERROR: Step failed with exit code %errorlevel%
exit /b %errorlevel%
