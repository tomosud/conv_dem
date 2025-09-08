@echo off
cd /d "%~dp0"
echo Starting EXR Heightmap Viewer server...
echo Open http://localhost:8000 in your browser
echo Press Ctrl+C to stop the server
python server.py
pause