param(
    [ValidateSet("PreWrite", "Audit")]
    [string]$Mode = "Audit"
)

$ErrorActionPreference = "Stop"

$services = @(
    # Phase 1
    "data-readiness"
    "legacy-integration"
    "integration-intelligence"
    "configuration-assurance"
    "release-assurance"
    "api-gateway"
    "audit-sink"

    # Phase 2
    "quality-intelligence"
    "diagnostic"
    "connected-service"

    # Phase 3
    "test-lab"
    "security-compliance"
    "ota-risk"

    # Phase 4
    "knowledge-copilot"
)

function Test-ServiceContract {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Service
    )

    foreach ($extension in @("yaml", "yml", "json")) {

        $openApi = Join-Path `
            $repoRoot `
            "contracts/openapi/$Service.$extension"

        $asyncApi = Join-Path `
            $repoRoot `
            "contracts/asyncapi/$Service.$extension"

        if (Test-Path -LiteralPath $openApi -PathType Leaf) {
            return $true
        }

        if (Test-Path -LiteralPath $asyncApi -PathType Leaf) {
            return $true
        }
    }

    $protoDirectory = Join-Path `
        $repoRoot `
        "contracts/proto/$Service"

    if (Test-Path -LiteralPath $protoDirectory -PathType Container) {

        $protoFiles = @(
            Get-ChildItem `
                -LiteralPath $protoDirectory `
                -Filter "*.proto" `
                -File
        )

        if ($protoFiles.Count -gt 0) {
            return $true
        }
    }

    return $false
}

function Assert-ServiceContract {
    param([string]$Service)

    if ($Service -notin $services) {
        throw "Unknown service: $Service"
    }

    if (-not (Test-ServiceContract -Service $Service)) {
        throw @"
CONTRACT VIOLATION: services/$Service

No API contract was found.

Create one of the following first:

contracts/openapi/$Service.yaml
contracts/asyncapi/$Service.yaml
contracts/proto/$Service/*.proto

Contract-first development is required.
"@
    }

    Write-Host "[PASS] Contract exists: $Service"
}

try {

    $repoRoot = git rev-parse --show-toplevel

    if ($LASTEXITCODE -ne 0 -or -not $repoRoot) {
        throw "Unable to locate Git repository."
    }

    $repoRoot = [IO.Path]::GetFullPath($repoRoot)

    Set-Location -LiteralPath $repoRoot

    Write-Host "[Contract Guard] Mode: $Mode"

    $affectedServices = @()

    if ($Mode -eq "PreWrite") {

        $rawInput = [Console]::In.ReadToEnd()

        if ([string]::IsNullOrWhiteSpace($rawInput)) {
            throw "Missing Kiro hook input."
        }

        $event = $rawInput | ConvertFrom-Json

        $toolInput = $event.tool_input

        if ($null -eq $toolInput) {
            throw "Missing tool_input."
        }

        $paths = @()

        foreach ($field in @(
            "path",
            "file",
            "file_path",
            "filePath",
            "targetFile",
            "sourcePath",
            "destinationPath",
            "paths"
        )) {
            $property = $toolInput.PSObject.Properties[$field]

            if ($property -and $property.Value) {
                $paths += @($property.Value)
            }
        }

        if ($paths.Count -eq 0) {
            throw "Cannot determine proposed file path."
        }

        foreach ($path in $paths) {

            $fullPath = [IO.Path]::GetFullPath(
                (Join-Path $repoRoot ".")
            )

            if ([IO.Path]::IsPathRooted([string]$path)) {
                $fullPath = [IO.Path]::GetFullPath(
                    [string]$path
                )
            }
            else {
                $fullPath = [IO.Path]::GetFullPath(
                    (Join-Path $repoRoot ([string]$path))
                )
            }

            $rootPrefix = $repoRoot.TrimEnd(
                [char[]]@('\', '/')
            ) + [IO.Path]::DirectorySeparatorChar

            if (-not $fullPath.StartsWith(
                $rootPrefix,
                [StringComparison]::OrdinalIgnoreCase
            )) {
                throw "Path is outside repository: $path"
            }

            $relativePath = $fullPath.Substring(
                $rootPrefix.Length
            ).Replace('\', '/')

            if ($relativePath -match '^services/([^/]+)/') {
                $affectedServices += $Matches[1]
            }
        }

    }
    else {

        # Include tracked, staged and untracked changes.

        $tracked = @(
            git -c core.quotepath=false diff --name-only HEAD --
        )

        if ($LASTEXITCODE -ne 0) {
            throw "Unable to inspect tracked changes."
        }

        $untracked = @(
            git -c core.quotepath=false ls-files `
                --others `
                --exclude-standard
        )

        if ($LASTEXITCODE -ne 0) {
            throw "Unable to inspect untracked files."
        }

        $changed = @($tracked + $untracked)

        foreach ($path in $changed) {

            $normalized = $path.Replace('\', '/')

            if ($normalized -match '^services/([^/]+)/') {
                $affectedServices += $Matches[1]
            }
        }
    }

    $affectedServices = @(
        $affectedServices | Sort-Object -Unique
    )

    if ($affectedServices.Count -eq 0) {
        Write-Host "[PASS] No affected services."
        exit 0
    }

    foreach ($service in $affectedServices) {
        Assert-ServiceContract -Service $service
    }

    Write-Host "[PASS] Contract verification completed."

    exit 0
}
catch {
    [Console]::Error.WriteLine(
        "[Contract Guard] BLOCKED: $($_.Exception.Message)"
    )

    exit 2
}