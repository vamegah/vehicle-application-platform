# Stop hook: validates the working tree and, only when release-policy.json sets autoCommit (and autoPush),
# commits on the current task branch and pushes it. Never commits on a protected branch, never force-pushes.
# Changes reach main only through a pull request (git-workflow.md); after a push this prints the compare URL.
param([switch]$DryRun)
. "$PSScriptRoot/common.ps1"
try {
  $policy = Policy 'release-policy'
  $branch = [string](GitRun branch --show-current)
  if (!$branch -or $branch -in @($policy.protectedBranches) -or $branch -notmatch $policy.allowedBranchRegex) {
    throw "Branch not approved for automatic commits: '$branch' (expected $($policy.allowedBranchRegex))"
  }
  if (!(GitRun status --porcelain)) { Write-Output '[auto-commit] No changes'; exit 0 }
  if (GitRun diff --cached --name-only) { throw 'Existing staged changes; review manually' }

  '{}' | & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PSScriptRoot/validate-release.ps1"
  if ($LASTEXITCODE -ne 0) { throw 'Release validation failed; nothing committed' }
  if ($DryRun -or !$policy.autoCommit) { Write-Output '[auto-commit] Validation passed; automatic commit is disabled (autoCommit=false) or this is a dry run'; exit 0 }

  $changed = @(ChangedPaths)
  $scope = 'repo'
  foreach ($path in $changed) {
    if ($path -match '^services/([^/]+)/') { $scope = $Matches[1]; break }
    if ($path -match '^\.kiro/(hooks|policies)/') { $scope = 'hooks'; break }
    if ($path -match '^\.kiro/specs/') { $scope = 'spec'; break }
  }

  GitRun add -A -- | Out-Null
  '{}' | & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PSScriptRoot/validate-release.ps1"
  if ($LASTEXITCODE -ne 0) { throw 'Staged validation failed; inspect the index manually' }
  if (GitRun diff --name-only) { throw 'Working tree changed during validation' }
  GitRun commit -m "chore(${scope}): commit validated changes" | Out-Null

  if ($policy.autoPush) {
    $env:GIT_TERMINAL_PROMPT = '0'
    GitRun push -u origin "HEAD:refs/heads/$branch" | Out-Null
    $remote = [string](GitRun remote get-url origin)
    if ($remote -match 'github\.com[:/](.+?)(\.git)?$') {
      Write-Output "[auto-commit] Pushed $branch. Open or update the pull request: https://github.com/$($Matches[1])/compare/main...$branch?expand=1"
    }
  }
  exit 0
} catch {
  [Console]::Error.WriteLine("[auto-commit] $($_.Exception.Message)")
  exit 1
}
