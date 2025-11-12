#!/bin/bash
# Deploy Web Output to GitHub Pages (Linux version)
# This script pushes the web_output/ directory to GitHub for public hosting

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Configuration
GITHUB_REPO="${GITHUB_REPO:-}"
GITHUB_BRANCH="${GITHUB_BRANCH:-gh-pages}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "=========================================="
log "GitHub Pages Deployment"
log "=========================================="

# Check if web_output exists
if [ ! -d "web_output" ]; then
    log "ERROR: web_output/ directory not found!"
    log "Run 'python3 upload_results.py' first to prepare files"
    exit 1
fi

# Check if git is initialized
if [ ! -d ".git" ]; then
    log "Initializing git repository..."
    git init
    git config user.name "PRA Automation" 2>/dev/null || true
    git config user.email "pra@localhost" 2>/dev/null || true
fi

# Check if GitHub repo is configured
if [ -z "$GITHUB_REPO" ]; then
    log "WARNING: GITHUB_REPO environment variable not set"
    log "Skipping GitHub deployment"
    log ""
    log "To enable GitHub Pages deployment:"
    log "  1. Create a GitHub repository"
    log "  2. Set: export GITHUB_REPO='username/repo-name'"
    log "  3. Set: export GITHUB_BRANCH='gh-pages' (or 'main')"
    log "  4. Optional: export GITHUB_TOKEN='your-token' (for private repos)"
    exit 0
fi

log "Repository: $GITHUB_REPO"
log "Branch: $GITHUB_BRANCH"

# Check if remote exists
if ! git remote | grep -q "origin"; then
    log "Adding GitHub remote..."
    if [[ ! "$GITHUB_REPO" =~ ^https:// ]]; then
        GITHUB_REPO="https://github.com/$GITHUB_REPO.git"
    fi
    git remote add origin "$GITHUB_REPO"
fi

# Update remote URL if token provided
if [ -n "$GITHUB_TOKEN" ]; then
    log "Using GitHub token for authentication..."
    REPO_URL=$(git remote get-url origin)
    if [[ "$REPO_URL" =~ https://github.com/(.+) ]]; then
        REPO_PATH="${BASH_REMATCH[1]}"
        git remote set-url origin "https://$GITHUB_TOKEN@github.com/$REPO_PATH"
    fi
fi

# Stage web_output files
log "Staging web_output files..."
git add web_output/
git add web_output/**/* 2>/dev/null || true

# Check if there are changes
if [ -z "$(git status --porcelain)" ]; then
    log "No changes to deploy"
    exit 0
fi

# Commit changes
COMMIT_MSG="Update web output - $(date '+%Y-%m-%d %H:%M:%S')"
log "Committing changes..."
git commit -m "$COMMIT_MSG" >/dev/null 2>&1 || true

# Push to GitHub
log "Pushing to GitHub..."
if [ "$GITHUB_BRANCH" = "gh-pages" ]; then
    # Create orphan branch for gh-pages (first time only)
    if ! git branch -r | grep -q "origin/gh-pages"; then
        log "Creating gh-pages branch..."
        git checkout --orphan gh-pages >/dev/null 2>&1
        git rm -rf --cached . >/dev/null 2>&1 || true
        git add web_output/ >/dev/null 2>&1
        git commit -m "Initial gh-pages commit" >/dev/null 2>&1
    else
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
    fi
else
    git checkout "$GITHUB_BRANCH" >/dev/null 2>&1 || git checkout -b "$GITHUB_BRANCH" >/dev/null 2>&1
fi

git push -u origin "$GITHUB_BRANCH" --force >/dev/null 2>&1

log "SUCCESS: Deployed to GitHub!"
log ""
log "Your site will be available at:"
if [[ "$GITHUB_REPO" =~ github.com/(.+) ]]; then
    REPO_PATH="${BASH_REMATCH[1]}" | sed 's/\.git$//'
    log "  https://${REPO_PATH%.git}.github.io"
else
    REPO_PATH=$(echo "$GITHUB_REPO" | sed 's/\.git$//' | sed 's|https://github.com/||')
    log "  https://${REPO_PATH}.github.io"
fi
log ""
log "Note: It may take 1-2 minutes for GitHub Pages to update"

