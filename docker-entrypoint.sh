#!/bin/bash
# Docker entrypoint script for LLM-ROUTE
# Handles signal forwarding and startup logic

set -e

# Function to handle graceful shutdown
shutdown() {
    echo "Received shutdown signal, stopping LLM-ROUTE..."
    # Send SIGTERM to the Python process
    if [ -n "$PID" ]; then
        kill -TERM "$PID" 2>/dev/null || true
        # Wait for graceful shutdown (max 10 seconds)
        wait "$PID" 2>/dev/null || true
    fi
    exit 0
}

# Register signal handlers
trap shutdown SIGTERM SIGINT

# Check if running in Docker environment
if [ -f /.dockerenv ]; then
    export LLM_ROUTE_DOCKER=1
fi

# Auto-detect headless mode if no display service
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    # No display service available, force headless
    if [ "$LLM_ROUTE_HEADLESS" != "0" ]; then
        export LLM_ROUTE_HEADLESS=1
        echo "No display service detected, running in headless mode"
    fi
fi

# Generate admin password if not set
CONFIG_FILE="/app/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
    # Check if admin_password_hash is empty or not set
    if ! grep -q "admin_password_hash:.*\$2[aby]\$" "$CONFIG_FILE" 2>/dev/null; then
        echo ""
        echo "=============================================="
        echo "Generating admin password for Web Dashboard..."
        echo "=============================================="

        # Generate and set password using Python (handles volume mount correctly)
        RESULT=$(python -c "
import secrets
import bcrypt

config_file = '$CONFIG_FILE'

# Generate a random 16-character password
password = secrets.token_urlsafe(12)

# Generate bcrypt hash
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

# Read config
with open(config_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Update or add admin_password_hash
lines = content.split('\n')
new_lines = []
hash_added = False
for line in lines:
    if line.startswith('admin_password_hash:'):
        new_lines.append(f'admin_password_hash: {password_hash}')
        hash_added = True
    else:
        new_lines.append(line)

if not hash_added:
    # Add after log_level
    for i, line in enumerate(new_lines):
        if line.startswith('log_level:'):
            new_lines.insert(i + 1, f'admin_password_hash: {password_hash}')
            break

# Write back
with open(config_file, 'w', encoding='utf-8') as f:
    f.write('\n'.join(new_lines))

# Output password for the shell script to display
print(password)
")

        echo ""
        echo "=============================================="
        echo "ADMIN PASSWORD (SAVE THIS!): $RESULT"
        echo "=============================================="
        echo ""
    fi
fi

# Log startup info
echo "Starting LLM-ROUTE..."
echo "  Platform: $(uname -s)"
echo "  Headless: ${LLM_ROUTE_HEADLESS:-auto}"
echo "  Port: ${LLM_ROUTE_PORT:-8087}"

# Start the application
python -m src.main "$@" &
PID=$!

# Wait for the application to exit
wait "$PID"
