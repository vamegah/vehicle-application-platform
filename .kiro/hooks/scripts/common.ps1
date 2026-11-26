# Shared helpers for the Kiro hook scripts. Windows PowerShell 5.1 compatible. ASCII only.
$ErrorActionPreference = 'Stop'
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..')).TrimEnd('\', '/')
Set-Location -LiteralPath $Root

function Policy($name) {
  Get-Content -Raw -LiteralPath (Join-Path $Root ".kiro/policies/$name.json") | ConvertFrom-Json
}

function GitRun {
  $output = & git @args
  if ($LASTEXITCODE -ne 0) { throw "Git failed: git $($args -join ' ')" }
  $output
}

# Reads the hook event JSON from stdin. Returns $null when stdin is empty.
function EventInput {
  $raw = [Console]::In.ReadToEnd()
  if (!$raw -or !$raw.Trim()) { return $null }
  $raw | ConvertFrom-Json
}

# Collects every file path a tool call or file event refers to.
function EventPaths($event) {
  $paths = @()
  if ($null -eq $event) { return $paths }
  $sources = @($event, $event.tool_input, $event.toolInput, $event.input) | Where-Object { $null -ne $_ }
  $fields = @('path', 'filePath', 'file_path', 'file', 'targetFile', 'target_file', 'targetPath', 'target_path',
              'sourcePath', 'destinationPath', 'oldPath', 'newPath', 'paths')
  foreach ($source in $sources) {
    if ($source -is [string]) { continue }
    foreach ($field in $fields) {
      $property = $source.PSObject.Properties[$field]
      if ($property -and $property.Value) { $paths += @($property.Value | ForEach-Object { [string]$_ }) }
    }
  }
  @($paths | Where-Object { $_ } | Select-Object -Unique)
}

# Returns the repository-relative path with forward slashes, or throws when the path leaves the repository.
function RelPath([string]$path) {
  if (!$path -or $path -match '[\x00-\x1f*?<>|]') { throw "Invalid path: $path" }
  if ([IO.Path]::IsPathRooted($path)) { $full = [IO.Path]::GetFullPath($path) }
  else { $full = [IO.Path]::GetFullPath((Join-Path $Root $path)) }
  if ($full.TrimEnd('\', '/') -ieq $Root) { return '' }
  $prefix = $Root + [IO.Path]::DirectorySeparatorChar
  if (!$full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Outside repository: $path" }
  $full.Substring($prefix.Length).Replace('\', '/')
}

# Throws when a write to the path is not allowed in this session (Phase 1 scope).
function AssertPath([string]$path) {
  $rel = RelPath $path
  $cursor = Join-Path $Root $rel
  while ($cursor -and $cursor.TrimEnd('\', '/') -ine $Root) {
    if (Test-Path -LiteralPath $cursor) {
      if ((Get-Item -Force -LiteralPath $cursor).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point: $cursor" }
    }
    $cursor = Split-Path -Parent $cursor
  }
  $policy = Policy 'phase-scope'
  $name = ($rel -split '/')[-1]
  foreach ($rule in $policy.blockedPaths) {
    $isPrefix = $rule.EndsWith('/') -or $rule.EndsWith('.')
    if ($rel -ieq $rule.TrimEnd('/') -or $name -ieq $rule) { throw "Blocked path: $rel" }
    if ($isPrefix -and ($rel.StartsWith($rule, [StringComparison]::OrdinalIgnoreCase) -or $name.StartsWith($rule, [StringComparison]::OrdinalIgnoreCase))) { throw "Blocked path: $rel" }
  }
  if ($rel -match '^services/([^/]+)(/|$)') {
    $context = $Matches[1]
    if ($context -in @($policy.futureContexts)) {
      throw "Blocked: $rel belongs to a Phase 2-4 bounded context. This session implements Phase 1 only: $(@($policy.phase1Contexts) -join ', ')"
    }
  }
  $rel
}

function ChangedPaths {
  @(GitRun -c core.quotepath=false diff --name-only --no-renames HEAD --) +
  @(GitRun -c core.quotepath=false ls-files --others --exclude-standard) | Where-Object { $_ }
}

# Blocks a PreToolUse action: Kiro blocks on exit code 2 and shows stderr.
function Block([string]$message) {
  [Console]::Error.WriteLine($message)
  exit 2
}
