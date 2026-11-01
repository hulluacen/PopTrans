@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0.."
set "ROOT=%CD%"
set "PYINSTALLER_CONFIG_DIR=%ROOT%\.pyinstaller"
if not defined PY_CMD set "PY_CMD=python"

echo Checking the selected CUDA Python environment...
%PY_CMD% scripts\prepare_cuda.py
if errorlevel 1 goto failed

%PY_CMD% -m PyInstaller --noconfirm --clean --distpath "%ROOT%\dist-ai-CUDA" --workpath "%ROOT%\build-ai-CUDA" "%ROOT%\backend\ai_engine.spec"
if errorlevel 1 goto failed

echo CUDA engine ready: dist-ai-CUDA\ai_engine.exe
echo Keep CUDA and Vulkan packages in separate directories.
popd
exit /b 0

:failed
echo CUDA build failed. Install backend\requirements-gpu-cuda.txt in an isolated Python environment first.
popd
exit /b 1
