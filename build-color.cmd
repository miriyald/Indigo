@echo off
setlocal

set TTF=output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular.ttf
set UFO=source/TiroTelugu-Regular.ufo

echo === Colorize ===
python tools/colorize.py %TTF% --ufo %UFO% -v
if errorlevel 1 goto :error

echo.
echo === Generate viewer ===
python tools/generate_viewer.py %TTF% --ufo %UFO%
if errorlevel 1 goto :error

echo.
echo === Generate test page ===
python tools/fonttest.py output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular-Colorized.ttf
if errorlevel 1 goto :error

echo.
echo === Done ===
goto :eof

:error
echo.
echo ERROR: Step failed with exit code %errorlevel%
exit /b %errorlevel%
