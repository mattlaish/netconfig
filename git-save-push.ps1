# git-save-push.ps1
# Safe commit and push helper for project repositories

Write-Host "=== Git Save & Push ===" -ForegroundColor Cyan

# Check Git repository
if (-not (Test-Path ".git")) {
    Write-Host "ERROR: This folder is not a Git repository." -ForegroundColor Red
    exit 1
}

$currentFolder = Split-Path -Leaf (Get-Location)

$branch = git branch --show-current
$remote = git remote get-url origin 2>$null

Write-Host ""
Write-Host "Project folder : $currentFolder"
Write-Host "Branch         : $branch"
Write-Host "Remote         : $remote"
Write-Host ""

# Check branch
if ($branch -ne "main") {
    Write-Host "WARNING: You are not on main branch." -ForegroundColor Yellow
    $continue = Read-Host "Continue anyway? (y/n)"

    if ($continue -ne "y") {
        exit
    }
}

# Check remote name against folder name
$repoName = ""

if ($remote -match "/([^/]+)\.git$") {
    $repoName = $matches[1]
}
elseif ($remote -match "/([^/]+)$") {
    $repoName = $matches[1]
}

if ($repoName -and ($repoName -ne $currentFolder)) {

    Write-Host ""
    Write-Host "WARNING: Folder and GitHub repo do not match!" -ForegroundColor Red
    Write-Host "Folder : $currentFolder"
    Write-Host "Repo   : $repoName"

    $continue = Read-Host "Continue anyway? (y/n)"

    if ($continue -ne "y") {
        exit
    }
}

# Show changes
Write-Host ""
Write-Host "Current changes:" -ForegroundColor Cyan

git status

Write-Host ""

$confirm = Read-Host "Continue with git add, commit, and push? (y/n)"

if ($confirm -ne "y") {
    Write-Host "Cancelled."
    exit
}

$message = Read-Host "Commit message"

if ([string]::IsNullOrWhiteSpace($message)) {
    $message = "Update project files"
}

Write-Host ""
Write-Host "Adding files..." -ForegroundColor Cyan
git add .

Write-Host ""
Write-Host "Committing..." -ForegroundColor Cyan
git commit -m "$message"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Commit failed or nothing changed." -ForegroundColor Yellow
    exit
}

Write-Host ""
Write-Host "Pushing to GitHub..." -ForegroundColor Cyan
git push

if ($LASTEXITCODE -ne 0) {
    Write-Host "Push failed." -ForegroundColor Red
    exit
}

Write-Host ""
Write-Host "Completed successfully." -ForegroundColor Green

git status