@echo off
set "src_dir=%~dp0..\src"
set "temp_file=clang-format-temp"
:main
echo processing...
for /r %src_dir% %%f in (*.cpp *.hpp *.h *.c) do call:format_code %%f
del /f %temp_file%
echo done
pause
goto:eof

:format_code
clang-format "%~1" > %temp_file%
::fc  %~1 %temp_file% >nul&&echo unchanged|| move /y %temp_file% %~1
fc  %~1 %temp_file% >nul 2>&1
if errorlevel 1 (
    echo formatting %~1
    copy /y %temp_file% %~1
    )
goto:eof
