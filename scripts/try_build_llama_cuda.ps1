$vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
$venvPy = "d:\wrok\workPro\superAIAutoCutVideoPro\backend\.venv_pack_gpu\Scripts\python.exe"
$venvScripts = "d:\wrok\workPro\superAIAutoCutVideoPro\backend\.venv_pack_gpu\Scripts"

# Source vcvars64.bat using Invoke-CmdScript
$tempCmdScript = [System.IO.Path]::GetTempFileName() + ".cmd"
$tempOutputFile = [System.IO.Path]::GetTempFileName() + ".env"
try {
    $cmdContent = @"
@echo off
call "$vcvars" >nul 2>&1
set > "$tempOutputFile"
"@
    Set-Content -Path $tempCmdScript -Value $cmdContent -Encoding Default
    
    # Run the cmd script to get environment variables
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "cmd.exe"
    $psi.Arguments = "/c `"$tempCmdScript`""
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.CreateNoWindow = $true
    
    $p = [System.Diagnostics.Process]::Start($psi)
    $p.WaitForExit()
    
    # Read the environment variables set by vcvars64.bat
    $envVars = Get-Content -Path $tempOutputFile
    foreach ($line in $envVars) {
        $eqPos = $line.IndexOf('=')
        if ($eqPos -gt 0) {
            $name = $line.Substring(0, $eqPos)
            $value = $line.Substring($eqPos + 1)
            [Environment]::SetEnvironmentVariable($name, $value, [EnvironmentVariableTarget]::Process)
        }
    }
    
    # Now prepend venv scripts to PATH for cmake 4.3.2
    $env:PATH = "$venvScripts;$env:PATH"
    
    # Set cmake args for CUDA build
    $env:CMAKE_ARGS = "-DGGML_CUDA=on"
    $env:FORCE_CMAKE = "1"
    $env:CMAKE_GENERATOR = "Ninja"
    
    Write-Host "[+] cmake version:"
    & cmake --version
    
    Write-Host "[+] Building llama-cpp-python==0.3.16 with CUDA support..."
    & $venvPy -m pip install --force-reinstall --no-cache-dir --no-deps llama-cpp-python==0.3.16
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[+] Build successful!"
        & $venvPy -c "import llama_cpp; import llama_cpp.llama_cpp as ll; print('llama_cpp', getattr(llama_cpp, '__version__', None)); print('supports_gpu_offload', bool(ll.llama_supports_gpu_offload()))"
    } else {
        Write-Host "[x] Build failed with exit code $LASTEXITCODE"
    }
}
finally {
    Remove-Item $tempCmdScript -Force -ErrorAction SilentlyContinue
    Remove-Item $tempOutputFile -Force -ErrorAction SilentlyContinue
}
