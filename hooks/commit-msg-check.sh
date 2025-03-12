#!/bin/bash

COMMIT_MSG_FILE="$1"
COMMITTER_EMAIL=$(git config --get user.email)

# Define the target committer email
TARGET_EMAIL="llm@opioinc.com"

# Regex pattern to enforce "time-prompting" with valid values
PATTERN="time-prompting:\s*(S|M|L|XL)\b"

# Only enforce the rule if the committer is the specified user
if [[ "$COMMITTER_EMAIL" == "$TARGET_EMAIL" ]]; then
    if ! grep -Eq "$PATTERN" "$COMMIT_MSG_FILE"; then
        echo "ERROR: Commit message must include 'time-prompting: S|M|L|XL' (Enforced for $TARGET_EMAIL)"
        exit 1
    fi
    echo "✓ Commit message format check passed"
else
    echo "✓ Commit message check skipped (not $TARGET_EMAIL)"
fi

exit 0