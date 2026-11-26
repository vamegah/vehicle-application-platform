# PreToolUse hook: blocks writes to Phase 2-4 bounded contexts, outside the repository, or to blocked paths.
# -Repository checks every changed file in the working tree instead (used by validate-release.ps1).
param([switch]$Repository)
. "$PSScriptRoot/common.ps1"
try {
  if ($Repository) { $paths = @(ChangedPaths) }
  else {
    $event = EventInput
    if ($null -eq $event) { Block '[phase-scope] BLOCKED: missing hook input' }
    $paths = @(EventPaths $event)
    if (!$paths.Count) { Block '[phase-scope] BLOCKED: cannot determine the target path of this write' }
  }
  foreach ($path in $paths) { $null = AssertPath $path }
  exit 0
} catch {
  Block "[phase-scope] BLOCKED: $($_.Exception.Message)"
}
