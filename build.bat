@echo off
echo Building LLM-ROUTE...
.conda\Scripts\pyinstaller.exe build.spec --clean
echo.
echo Build complete! Executable: dist\llm-route.exe
pause
