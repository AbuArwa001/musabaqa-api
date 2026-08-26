#!/bin/bash

# Default port to 8000 if not set by the server environment
PORT=${PORT:-8000}

echo "Starting Musabaqa API on port $PORT..."

# Run uvicorn with proxy headers enabled (useful behind nginx/load balancers on a server)
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
