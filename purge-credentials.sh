#!/usr/bin/env bash
set -euo pipefail

REPO_SSH="git@github.com:DJx26/InventoM.git"
MIRROR_DIR="InventoM.git"
TARGET_PATH="data/credentials.json"

echo "WARNING: This will rewrite history and force-push to ${REPO_SSH}."
read -p "Type YES to continue: " CONFIRM
if [ "$CONFIRM" != "YES" ]; then
  echo "Aborted."
  exit 1
fi

# Ensure git-filter-repo is available
if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo not found. Please install it (pip3 install --user git-filter-repo) and re-run."
  exit 2
fi

# Remove any existing mirror dir to avoid confusion
if [ -d "$MIRROR_DIR" ]; then
  echo "Removing existing $MIRROR_DIR"
  rm -rf "$MIRROR_DIR"
fi

echo "Cloning repository as a mirror..."
git clone --mirror "$REPO_SSH" "$MIRROR_DIR"

cd "$MIRROR_DIR"

echo "Running git-filter-repo to remove path: $TARGET_PATH"
# --invert-paths means remove the given path(s) from all commits
git filter-repo --path "$TARGET_PATH" --invert-paths

echo "Expiring reflogs and garbage collecting..."
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo "Force-pushing cleaned history to origin (all branches and tags)..."
git push --force --all
git push --force --tags

echo "Done. Mirror directory retained at $(pwd) for inspection."
echo

echo "POST-CLEANUP ACTIONS YOU MUST DO NEXT:"
echo "1) Revoke and rotate the exposed Google service account key immediately."
echo "2) Tell all collaborators to reclone the repository (do NOT pull)."
echo "   Example: git clone git@github.com:DJx26/InventoM.git"
echo "3) Check CI/CD providers, forks, release assets, and backups for copies of the secret."
echo 

echo "Notes: If GitHub displays cached references (e.g., in forks or other mirrors), you may need to contact GitHub Support."