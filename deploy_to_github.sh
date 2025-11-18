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

# Save current branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream

# Step 1: Commit and push main branch changes first (if on main)
if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
    log "Checking for uncommitted changes on $CURRENT_BRANCH branch..."
    STATUS=$(git status --porcelain)
    if [ -n "$STATUS" ]; then
        log "Found uncommitted changes on $CURRENT_BRANCH, committing..."
        
        # Stage all changes (except web_output which is in .gitignore)
        git add -A >/dev/null 2>&1
        git reset HEAD web_output/ >/dev/null 2>&1  # Don't commit web_output to main
        
        MAIN_COMMIT_MSG="Update source files - $(date '+%Y-%m-%d %H:%M:%S')"
        git commit -m "$MAIN_COMMIT_MSG" >/dev/null 2>&1
        
        if [ $? -eq 0 ]; then
            log "Pushing $CURRENT_BRANCH branch to origin..."
            git push origin "$CURRENT_BRANCH" >/dev/null 2>&1
            if [ $? -eq 0 ]; then
                log "Successfully pushed $CURRENT_BRANCH branch"
            else
                log "Warning: Failed to push $CURRENT_BRANCH (continuing with deployment)"
            fi
        fi
    else
        log "No uncommitted changes on $CURRENT_BRANCH branch"
    fi
fi

# Fetch latest from remote
log "Fetching latest from remote..."
git fetch origin >/dev/null 2>&1
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes

# Push to GitHub
log "Deploying to GitHub Pages..."
if [ "$GITHUB_BRANCH" = "gh-pages" ]; then
    # Check if remote branch exists
    REMOTE_BRANCH_EXISTS=$(git branch -r | grep -q "origin/gh-pages" && echo "yes" || echo "no")
    LOCAL_BRANCH_EXISTS=$(git branch | grep -q "^\s*gh-pages$" && echo "yes" || echo "no")
    
    if [ "$REMOTE_BRANCH_EXISTS" = "no" ]; then
        # Create orphan branch for gh-pages (first time only)
        log "Creating gh-pages branch..."
        
        # Stash any uncommitted changes
        HAS_CHANGES=$(git status --porcelain)
        if [ -n "$HAS_CHANGES" ]; then
            log "Stashing uncommitted changes..."
            git stash push -m "Auto-stash before gh-pages deployment" >/dev/null 2>&1
        fi
        
        git checkout --orphan gh-pages >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            log "ERROR: Failed to create gh-pages branch"
            exit 1
        fi
        git rm -rf --cached . >/dev/null 2>&1 || true
        
        # Copy web_output contents to root (GitHub Pages needs files at root)
        log "Copying web_output files to root..."
        if [ -d "web_output" ]; then
            cp -r web_output/* .
        fi
        
        git add -f . >/dev/null 2>&1
        git commit -m "Initial gh-pages commit" >/dev/null 2>&1
    else
        log "Switching to gh-pages branch..."
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
        
        # Stash any uncommitted changes before switching
        HAS_CHANGES=$(git status --porcelain)
        if [ -n "$HAS_CHANGES" ]; then
            log "Stashing uncommitted changes..."
            git stash push -m "Auto-stash before gh-pages deployment" >/dev/null 2>&1
        fi
        
        # Try to checkout existing local branch
        if [ "$LOCAL_BRANCH_EXISTS" = "yes" ]; then
            git checkout gh-pages >/dev/null 2>&1
        else
            # Create local branch tracking remote
            git checkout -b gh-pages origin/gh-pages >/dev/null 2>&1
        fi
        
        if [ $? -ne 0 ]; then
            # Force checkout by resetting the branch
            log "Force resetting gh-pages branch..."
            if [ "$LOCAL_BRANCH_EXISTS" = "yes" ]; then
                git branch -D gh-pages >/dev/null 2>&1
            fi
            git checkout -b gh-pages origin/gh-pages >/dev/null 2>&1
            if [ $? -ne 0 ]; then
                log "ERROR: Failed to checkout gh-pages branch"
                exit 1
            fi
        fi
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
=======
        git checkout gh-pages >/dev/null 2>&1 || git checkout -b gh-pages >/dev/null 2>&1
>>>>>>> Stashed changes
        
        # Verify we're on gh-pages
        CHECK_BRANCH=$(git rev-parse --abbrev-ref HEAD)
        if [ "$CHECK_BRANCH" != "gh-pages" ]; then
            log "ERROR: Not on gh-pages branch! Current: $CHECK_BRANCH"
            exit 1
        fi
        
        # Copy web_output contents to root
        log "Copying web_output files to root..."
        # Remove existing files (except .git and web_output)
        find . -mindepth 1 -maxdepth 1 ! -name '.git' ! -name 'web_output' -exec rm -rf {} + 2>/dev/null || true
        if [ -d "web_output" ]; then
            cp -r web_output/* .
        fi
    fi
    
    # Verify we're still on gh-pages before committing
    VERIFY_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [ "$VERIFY_BRANCH" != "gh-pages" ]; then
        log "ERROR: Not on gh-pages branch! Current: $VERIFY_BRANCH"
        exit 1
    fi
    
    # Stage all files at root
    log "Staging files..."
    git add -f . >/dev/null 2>&1
    # Remove web_output from staging (we don't want the folder, just its contents at root)
    git reset HEAD web_output/ >/dev/null 2>&1 || true
    
else
    git checkout "$GITHUB_BRANCH" >/dev/null 2>&1 || git checkout -b "$GITHUB_BRANCH" >/dev/null 2>&1
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
    if [ $? -ne 0 ]; then
        log "ERROR: Failed to checkout $GITHUB_BRANCH branch"
        exit 1
    fi
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
    # For non-gh-pages branches, just add web_output as-is
    git add -f web_output/ >/dev/null 2>&1
fi

# Check if there are changes
HAS_CHANGES=$(git status --porcelain)
COMMIT_MSG="Update web output - $(date '+%Y-%m-%d %H:%M:%S')"

# Final verification of branch before commit
FINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)
log "Committing on branch: $FINAL_BRANCH"

if [ -n "$HAS_CHANGES" ]; then
    log "Committing changes..."
    git commit -m "$COMMIT_MSG" >/dev/null 2>&1 || true
else
    log "No file changes detected, creating empty commit to update timestamp..."
    git commit --allow-empty -m "$COMMIT_MSG" >/dev/null 2>&1 || true
fi

log "Pushing to origin/$GITHUB_BRANCH..."
git push -u origin "$GITHUB_BRANCH" --force >/dev/null 2>&1

log "SUCCESS: Deployed to GitHub!"
log ""
log "Your site will be available at:"
if [[ "$GITHUB_REPO" =~ github.com/(.+) ]]; then
    REPO_PATH=$(echo "${BASH_REMATCH[1]}" | sed 's/\.git$//')
else
    REPO_PATH=$(echo "$GITHUB_REPO" | sed 's/\.git$//' | sed 's|https://github.com/||')
fi
# Format: username/repo -> https://username.github.io/repo
IFS='/' read -ra PARTS <<< "$REPO_PATH"
if [ ${#PARTS[@]} -eq 2 ]; then
    USERNAME="${PARTS[0]}"
    REPO_NAME="${PARTS[1]}"
    log "  https://${USERNAME}.github.io/${REPO_NAME}"
else
    log "  https://${REPO_PATH}.github.io"
fi
log ""
log "Note: It may take 1-2 minutes for GitHub Pages to update"

# Switch back to original branch
if [ -n "$CURRENT_BRANCH" ] && [ "$CURRENT_BRANCH" != "$GITHUB_BRANCH" ]; then
    log "Switching back to $CURRENT_BRANCH branch..."
    git checkout "$CURRENT_BRANCH" >/dev/null 2>&1 || true
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
<<<<<<< Updated upstream
    
    # Restore stashed changes if any
    STASH_LIST=$(git stash list 2>&1)
    if echo "$STASH_LIST" | grep -q "Auto-stash before gh-pages deployment"; then
        log "Restoring stashed changes..."
        git stash pop >/dev/null 2>&1 || true
    fi
fi

=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
=======
fi
>>>>>>> Stashed changes
