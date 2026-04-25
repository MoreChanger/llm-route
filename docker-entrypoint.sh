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
