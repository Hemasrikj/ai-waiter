#!/bin/bash
set -e

# Step 1: Check current state
git log --oneline --all | head -20
git status

# Step 2: Clean up any leftover branch from a previous failed run
git branch -D new-main 2>/dev/null || true

# Step 3: Create orphan branch and squash all history into one commit
git checkout --orphan new-main
git add -A
git commit -m "ai-waiter"

# Step 4: Replace main with the new single-commit branch
git branch -D main
git branch -m main
git push --force origin main
git branch --set-upstream-to=origin/main main
git remote set-head origin main

# Step 5: Verify
git log --oneline --all
