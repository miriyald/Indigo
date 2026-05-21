@echo off
setlocal

set TTF=output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular.ttf
set UFO=source/TiroTelugu-Regular.ufo

echo === Step 1: Generate mapping ===
python tools/generate_mapping.py %TTF% --ufo %UFO%
if errorlevel 1 goto :error

echo.
echo === Step 2: Apply color ===
python tools/add_color.py --style manual --ufo %UFO% %TTF%
if errorlevel 1 goto :error

echo.
echo === Step 3: Generate viewer ===
python tools/generate_viewer.py %TTF% --ufo %UFO%
if errorlevel 1 goto :error

echo.
echo === Step 4: Generate test page ===
python tools/fonttest.py output/indigo-telugu/TiroTelugu/TTF/TiroTelugu-Regular-ColorManual.ttf
if errorlevel 1 goto :error

echo.
echo === Done ===
goto :eof

:error
echo.
echo ERROR: Step failed with exit code %errorlevel%
exit /b %errorlevel%
