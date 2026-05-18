param(
  [string[]]$Path = @("scripts\*.ps1")
)

$ErrorActionPreference = "Stop"

$rootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $rootDir

$files = foreach ($item in $Path) {
  Get-ChildItem -Path $item -File -ErrorAction Stop
}

$hasErrors = $false
foreach ($file in $files) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$errors) | Out-Null

  if ($errors -and $errors.Count -gt 0) {
    $hasErrors = $true
    Write-Host "Syntax errors in $($file.FullName):" -ForegroundColor Red
    foreach ($err in $errors) {
      $start = $err.Extent.StartLineNumber
      $end = $err.Extent.EndLineNumber
      Write-Host ("  line {0}-{1}: {2}" -f $start, $end, $err.Message) -ForegroundColor Red
    }
  } else {
    Write-Host "OK $($file.FullName)" -ForegroundColor Green
  }
}

if ($hasErrors) {
  exit 1
}
