# PostFileSave hook: runs the tests of every project touched by a saved .java, .py, .ts, or .tsx file.
#  - services/<context>/...: nearest folder with pom.xml (mvn test, no ITs) or pyproject.toml / requirements.txt / setup.py (pytest)
#  - services/release-assurance/...: also the inference-sidecar pytest suite
#  - apps/web/...: npm test, when package.json defines a test script
#  - scripts/...: the dependency pin check fixture tests
# pytest exit code 5 (no tests collected) counts as a pass. Exit 2 with the failing projects on stderr.
. "$PSScriptRoot/common.ps1"

function Invoke-InFolder([string]$folder, [string]$exe, [string[]]$arguments, [int[]]$okCodes = @(0)) {
  $command = Get-Command $exe -ErrorAction SilentlyContinue | Select-Object -First 1
  if (!$command) { return "$folder : '$exe' is not installed or not on PATH" }
  Push-Location -LiteralPath (Join-Path $Root $folder)
  try {
    Write-Host "[run-tests] $folder : $exe $($arguments -join ' ')"
    & $command.Source @arguments | Out-Host
    if ($LASTEXITCODE -notin $okCodes) { return "$folder : $exe exited $LASTEXITCODE" }
  } finally { Pop-Location }
  $null
}

try {
  $event = EventInput
  $targets = @()
  foreach ($path in @(EventPaths $event)) {
    try { $targets += RelPath $path } catch { }   # files outside the repository are ignored
  }
  $targets = @($targets | Where-Object { $_ -match '\.(java|py|ts|tsx)$' } | Select-Object -Unique)
  if (!$targets.Count) { exit 0 }

  $roots = @()
  foreach ($rel in $targets) {
    if ($rel -match '^services/') {
      $dir = Split-Path -Parent $rel
      while ($dir -and $dir.Replace('\', '/') -match '^services(/|$)') {
        $full = Join-Path $Root $dir
        if (@('pom.xml', 'pyproject.toml', 'requirements.txt', 'setup.py') | Where-Object { Test-Path -LiteralPath (Join-Path $full $_) }) {
          $roots += $dir.Replace('\', '/'); break
        }
        if ($dir.Replace('\', '/') -eq 'services') { break }
        $dir = Split-Path -Parent $dir
      }
      if ($rel -match '^services/release-assurance/') {
        $sidecar = 'services/release-assurance/inference-sidecar'
        if (@('pyproject.toml', 'requirements.txt', 'setup.py') | Where-Object { Test-Path -LiteralPath (Join-Path (Join-Path $Root $sidecar) $_) }) { $roots += $sidecar }
      }
    } elseif ($rel -match '^apps/web/') {
      $roots += 'apps/web'
    } elseif ($rel -match '^scripts/' -and (Test-Path -LiteralPath (Join-Path $Root 'scripts/tests/test_check_dependency_pins.py'))) {
      $roots += 'scripts'
    }
  }
  $roots = @($roots | Select-Object -Unique)

  $failures = @()
  # Note: PowerShell variable names are case-insensitive, so the loop variable must not be called $root ($Root is the repository root).
  foreach ($project in $roots) {
    $full = Join-Path $Root $project
    if ($project -eq 'apps/web') {
      $package = Join-Path $full 'package.json'
      if ((Test-Path -LiteralPath $package) -and (Get-Content -Raw -LiteralPath $package | ConvertFrom-Json).scripts.test) {
        $failures += Invoke-InFolder $project 'npm.cmd' @('test', '--silent')
      }
    } elseif ($project -eq 'scripts') {
      Push-Location -LiteralPath $Root
      try {
        & python -m unittest discover -s scripts/tests -p 'test_check_dependency_pins.py' 2>&1 | Out-Host
        if ($LASTEXITCODE -ne 0) { $failures += "scripts : pin check tests exited $LASTEXITCODE" }
      } finally { Pop-Location }
    } elseif (Test-Path -LiteralPath (Join-Path $full 'pom.xml')) {
      $failures += Invoke-InFolder $project 'mvn' @('-q', '-DskipITs', 'test')
    } else {
      $failures += Invoke-InFolder $project 'pytest' @('-q', '--maxfail=1') @(0, 5)
    }
  }
  $failures = @($failures | Where-Object { $_ })
  if ($failures.Count) {
    [Console]::Error.WriteLine("[run-tests] FAILED:`n" + ($failures -join "`n"))
    exit 2
  }
  exit 0
} catch {
  [Console]::Error.WriteLine("[run-tests] ERROR: $($_.Exception.Message)")
  exit 2
}
