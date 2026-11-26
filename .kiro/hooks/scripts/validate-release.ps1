# ============================================================
# Kiro Development Governance Framework
# Script: validate-release.ps1
# Compatible with Windows PowerShell 5.1+
# ============================================================

$ErrorActionPreference = 'Stop'

$started = Get-Date
$script:passed = 0

# ============================================================
# Execute a validation gate
# ============================================================

function Invoke-Gate {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    $timer = [Diagnostics.Stopwatch]::StartNew()

    Write-Host "`n[RUN] $Name" -ForegroundColor Cyan

    & $Action

    $script:passed++

    Write-Host (
        "[PASS] {0} ({1:N2}s)" -f `
            $Name, $timer.Elapsed.TotalSeconds
    ) -ForegroundColor Green
}

# ============================================================
# Execute a required PowerShell validator
# ============================================================

function Invoke-Validator {
    param(
        [string]$Name,
        [string[]]$Arguments = @()
    )

    $file = Join-Path $PSScriptRoot "$Name.ps1"

    if (!(Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Required validator missing: $file"
    }

    '{}' | & powershell.exe `
        -NoProfile `
        -NonInteractive `
        -ExecutionPolicy Bypass `
        -File $file `
        @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed (exit $LASTEXITCODE)"
    }
}

# ============================================================
# Detect potentially sensitive files
# ============================================================

function Assert-SensitivePaths {

    foreach ($path in @(ChangedPaths)) {

        if ($path -match '(?i)(^|/)(\.env(?:\..*)?|id_rsa|id_ed25519|credentials|.*\.(pem|pfx|p12|key))$') {
            throw "Potential secret file: $path"
        }
    }
}

# ============================================================
# Main release validation
# ============================================================

try {

    # Load shared governance functions

    . "$PSScriptRoot/common.ps1"

    Write-Host `
        '=== KIRO RELEASE VALIDATION ===' `
        -ForegroundColor Cyan

    # --------------------------------------------------------
    # Gate 1: Git repository validation
    # --------------------------------------------------------

    Invoke-Gate 'Git repository validation' {

        $gitRoot = GitRun rev-parse --show-toplevel

        if ([IO.Path]::GetFullPath($gitRoot) -ne $Root) {
            throw 'Governance scripts must be inside the repository root.'
        }

        GitRun rev-parse --verify HEAD | Out-Null
    }

    # --------------------------------------------------------
    # Gate 2: Phase scope enforcement
    # --------------------------------------------------------

    Invoke-Gate 'Phase scope enforcement' {

        Invoke-Validator `
            'check-phase-scope' `
            @('-Repository')
    }

    # --------------------------------------------------------
    # Gate 3: Dependency pin enforcement
    # --------------------------------------------------------

    Invoke-Gate 'Dependency pin enforcement' {

        Invoke-Validator 'check-dependency-pins' @('-Repository')
    }

    # --------------------------------------------------------
    # Gate 4: API contract verification
    # --------------------------------------------------------

    Invoke-Gate 'API contract verification' {

        Invoke-Validator `
            'verify-contract' `
            @('-Mode', 'Audit')
    }

    # --------------------------------------------------------
    # Gate 5: Sensitive filename detection
    # --------------------------------------------------------

    Invoke-Gate 'Sensitive filename detection' {

        Assert-SensitivePaths
    }

    # --------------------------------------------------------
    # Gate 6: Git diff and merge conflict validation
    # --------------------------------------------------------

    Invoke-Gate 'Git diff validation' {

        GitRun diff --check HEAD --

        $unmerged = @(GitRun ls-files -u)

        if ($unmerged.Count -gt 0) {
            throw 'Unmerged Git index entries detected.'
        }
    }

    # --------------------------------------------------------
    # Load centralized release policy
    # --------------------------------------------------------

    $policy = Policy 'release-policy'

    if (
        $null -eq $policy.checks -or
        @($policy.checks).Count -eq 0
    ) {
        throw 'Configure at least one release check in release-policy.json.'
    }

    # --------------------------------------------------------
    # Gates 7-10: Configured quality checks
    #
    # Supports:
    # - Lint
    # - Type checking
    # - Unit tests
    # - Integration tests
    # - Build validation
    # - Security scanning
    # - Contract syntax validation
    # --------------------------------------------------------

    foreach ($check in $policy.checks) {

        if ($check.requiresPath -and !(Test-Path -LiteralPath (Join-Path $Root $check.requiresPath))) {
            Write-Host "[SKIP] $($check.name): $($check.requiresPath) is not on this branch"
            continue
        }

        $exe = [string]$check.executable

        $checkArgs = @(
            $check.arguments | ForEach-Object {
                [string]$_
            }
        )

        if ([string]::IsNullOrWhiteSpace($exe)) {
            throw 'Missing check executable.'
        }

        $command = Get-Command `
            $exe `
            -CommandType Application `
            -ErrorAction Stop |
            Select-Object -First 1

        Invoke-Gate (
            "$exe " + ($checkArgs -join ' ')
        ) {

            Set-Location -LiteralPath $Root

            & $command.Source @checkArgs

            if ($LASTEXITCODE -ne 0) {

                throw "Release check failed: $exe (exit $LASTEXITCODE)"
            }
        }
    }

    # --------------------------------------------------------
    # Gate 11: Final repository policy revalidation
    #
    # Tests and build commands may generate or modify files.
    # Recheck repository policies before permitting a commit.
    # --------------------------------------------------------

    Invoke-Gate 'Final repository policy revalidation' {

        Invoke-Validator `
            'check-phase-scope' `
            @('-Repository')

        Invoke-Validator 'check-dependency-pins' @('-Repository')

        Invoke-Validator `
            'verify-contract' `
            @('-Mode', 'Audit')

        Assert-SensitivePaths

        GitRun diff --check HEAD --

        if (@(GitRun ls-files -u).Count -gt 0) {
            throw 'Unmerged Git index entries detected.'
        }
    }

    # --------------------------------------------------------
    # Release validation summary
    # --------------------------------------------------------

    Write-Host (
        "`n[PASS] Release validation complete. " +
        "Gates passed: {0}. Elapsed: {1:N2}s" -f `
            $script:passed,
            ((Get-Date) - $started).TotalSeconds
    ) -ForegroundColor Green

    exit 0
}
catch {

    [Console]::Error.WriteLine(
        "[BLOCKED] Release validation failed: " +
        $_.Exception.Message
    )

    exit 1
}