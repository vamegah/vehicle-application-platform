# PreToolUse hook for shell tools: blocks commands that git-workflow.md and the safety rules forbid
# (force push, push to main, reset --hard, clean -f, branch -D, --no-verify, git config, rm -rf).
# Everything else is allowed.
. "$PSScriptRoot/common.ps1"
try {
  $event = EventInput
  if ($null -eq $event) { Block '[shell-scope] BLOCKED: missing hook input' }
  $toolInput = $event.tool_input
  if ($null -eq $toolInput) { $toolInput = $event }
  $command = $toolInput.command
  if ($null -eq $command) { exit 0 }  # e.g. a stop action with no command
  if ($command -isnot [string]) { Block '[shell-scope] BLOCKED: unexpected shell payload' }
  $policy = Policy 'release-policy'
  foreach ($rule in @($policy.deniedShellPatterns)) {
    if ($command -match $rule.pattern) {
      Block "[shell-scope] BLOCKED: $($rule.reason). Run it manually if you really intend it."
    }
  }
  exit 0
} catch {
  Block "[shell-scope] BLOCKED: $($_.Exception.Message)"
}
