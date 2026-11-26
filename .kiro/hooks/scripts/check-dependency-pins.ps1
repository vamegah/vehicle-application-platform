# PreToolUse hook: blocks a write to a dependency manifest whose new content has a loose version
# (range operator, caret or tilde range, wildcard, latest) or a MinIO reference.
# -Repository runs the full ledger check (scripts/check-dependency-pins) instead (used by validate-release.ps1).
param([switch]$Repository)
. "$PSScriptRoot/common.ps1"
$policy = Policy 'dependency-policy'

if ($Repository) {
  $checker = Join-Path $Root $policy.fullChecker
  if (!(Test-Path -LiteralPath $checker -PathType Leaf)) {
    Write-Output "[dependency-pins] $($policy.fullChecker) not present on this branch; full ledger check skipped"
    exit 0
  }
  & python $checker
  if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine('[dependency-pins] full ledger check failed'); exit 1 }
  exit 0
}

try {
  $event = EventInput
  if ($null -eq $event) { Block '[dependency-pins] BLOCKED: missing hook input' }
  $manifests = @()
  foreach ($path in @(EventPaths $event)) {
    $rel = RelPath $path
    $name = ($rel -split '/')[-1]
    $isManifest = $name -in @($policy.manifestFileNames)
    foreach ($pattern in @($policy.manifestFilePatterns)) { if ($name -match $pattern) { $isManifest = $true } }
    if ($isManifest) { $manifests += $rel }
  }
  if (!$manifests.Count) { exit 0 }

  $toolInput = $event.tool_input
  if ($null -eq $toolInput) { $toolInput = $event }
  $content = @()
  foreach ($field in @('text', 'content', 'newStr', 'new_str', 'file_text', 'newContent')) {
    $property = $toolInput.PSObject.Properties[$field]
    if ($property -and $property.Value) { $content += [string]$property.Value }
  }
  if (!$content.Count) { exit 0 }

  $lineNumber = 0
  foreach ($line in (($content -join "`n") -split "`r?`n")) {
    $lineNumber++
    $exempt = $false
    foreach ($pattern in @($policy.exemptLinePatterns)) { if ($line -match $pattern) { $exempt = $true } }
    if ($exempt) { continue }
    foreach ($rule in @($policy.loosePatterns)) {
      if ($line -match $rule.pattern) {
        Block ("[dependency-pins] BLOCKED: {0} line {1}: {2}: {3}`nEvery dependency must be exactly pinned and recorded in DEPENDENCIES.lock.md." -f ($manifests -join ', '), $lineNumber, $rule.reason, $line.Trim())
      }
    }
  }
  exit 0
} catch {
  Block "[dependency-pins] BLOCKED: $($_.Exception.Message)"
}
