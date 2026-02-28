@echo off
setlocal

echo Setting up Visual Studio build environment...
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

echo Activating backend\.venv_pack_gpu...
call "%~dp0..\.\.venv_pack_gpu\Scripts\activate.bat"

echo Installing build tool (ninja)...
python -m pip install --upgrade ninja

echo Installing llama-cpp-python with CUDA (GGML_CUDA)...
set CMAKE_ARGS=-DGGML_CUDA=on
set FORCE_CMAKE=1
set CMAKE_GENERATOR=Ninja

python -m pip install --force-reinstall --no-cache-dir --no-deps "llama-cpp-python==0.3.16"

python -c "import llama_cpp; import llama_cpp.llama_cpp as ll; print('llama_cpp', llama_cpp.__version__); print('supports_gpu_offload', ll.llama_supports_gpu_offload())"

