@echo off

python -m compileall . -q

REM Check if the "thonny" folder exists
if not exist "thonny" (
    echo The "thonny" folder does not exist.
    exit /b
)

REM Create the "output" directory if it doesn't exist
if not exist "output" (
    mkdir "output"
)

REM Copy the "thonny" folder to "output/thonny"
xcopy "thonny" "output\thonny" /E /I /H /Y

copy "__pycache__\index.cpython-310.pyc" "output" /Y

echo Copying completed successfully!
pause
