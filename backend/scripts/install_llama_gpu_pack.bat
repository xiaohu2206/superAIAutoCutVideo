@echo off
setlocal

echo Setting up Visual Studio build environment...
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

echo Activating backend\.venv_pack_gpu...
set VENV_DIR=%~dp0..\.\.venv_pack_gpu
set PYTHON_EXE=%VENV_DIR%\Scripts\python.exe
if exist "%VENV_DIR%\Scripts\activate.bat" (
  call "%VENV_DIR%\Scripts\activate.bat"
) else (
  echo activate.bat not found, using "%PYTHON_EXE%"
)

echo Installing build tool (ninja)...
"%PYTHON_EXE%" -m pip install --upgrade ninja

echo Installing llama-cpp-python with CUDA (GGML_CUDA)...
set CMAKE_ARGS=-DGGML_CUDA=on
set FORCE_CMAKE=1
set CMAKE_GENERATOR=Ninja

"%PYTHON_EXE%" -m pip install --force-reinstall --no-cache-dir --no-deps "llama-cpp-python==0.3.16"

"%PYTHON_EXE%" -c "import llama_cpp; import llama_cpp.llama_cpp as ll; print('llama_cpp', llama_cpp.__version__); print('supports_gpu_offload', ll.llama_supports_gpu_offload())"

