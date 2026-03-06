#!/bin/bash

# Hitchhiking Map Project - Local Development Script
# This script sets up and runs the development environment using a Python virtual environment

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to kill processes on port 4242
kill_port_4242() {
    print_status "Checking for existing processes on port 4242..."
    local pids=$(lsof -ti:4242 2>/dev/null)
    if [ ! -z "$pids" ]; then
        print_warning "Found existing processes on port 4242: $pids"
        print_status "Killing existing processes..."
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 2
        # Verify they're gone
        local remaining=$(lsof -ti:4242 2>/dev/null)
        if [ ! -z "$remaining" ]; then
            print_warning "Some processes still running, forcing kill..."
            echo "$remaining" | xargs kill -9 2>/dev/null || true
        fi
        print_success "Port 4242 is now free"
    else
        print_status "Port 4242 is available"
    fi
}

# Function to cleanup background processes
cleanup() {
    print_status "Cleaning up background processes..."
    if [ ! -z "$WATCH_PID" ]; then
        kill $WATCH_PID 2>/dev/null || true
    fi
    kill_port_4242
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Check if we're in the right directory
if [ ! -f "hitch/__init__.py" ]; then
    print_error "Please run this script from the project root directory"
    exit 1
fi

print_status "Starting Hitchhiking Map development environment with virtual environment..."

# Kill any existing processes on port 4242
kill_port_4242

# Check for Python
if ! command_exists python3; then
    print_error "Python 3 is required but not installed"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.12"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    print_warning "Python $PYTHON_VERSION detected. Recommended version is $REQUIRED_VERSION or higher."
fi

# Check for Node.js (needed for TypeScript compilation)
if ! command_exists node; then
    print_warning "Node.js not found. TypeScript compilation will be skipped."
    print_warning "Install Node.js to enable TypeScript compilation: https://nodejs.org/"
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    print_status "Creating virtual environment..."
    python3 -m venv .venv
    print_success "Virtual environment created"
else
    print_status "Virtual environment already exists"
fi

# Activate virtual environment
print_status "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
print_status "Upgrading pip..."
pip install --upgrade pip

# Install Python dependencies
print_status "Installing Python dependencies..."
pip install -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    if [ -f "example.env" ]; then
        print_warning ".env file not found, copying from example.env"
        cp example.env .env
        print_warning "Please edit .env file with your configuration before continuing"
        print_warning "Press Enter to continue or Ctrl+C to exit and configure .env"
        read
    else
        print_error ".env file not found and no example.env available"
        exit 1
    fi
fi

# Check for user-password.py
if [ ! -f "user-password.py" ]; then
    if [ -f "user-password.py.example" ]; then
        print_warning "user-password.py not found, copying from example"
        cp user-password.py.example user-password.py
        print_warning "Please edit user-password.py with your configuration"
    fi
fi

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p logs dist db

# Download database if it doesn't exist
if [ ! -f "db/points.sqlite" ]; then
    print_status "Downloading database..."
    curl -o db/points.sqlite https://hitchmap.com/dump.sqlite
    print_success "Database downloaded"
fi

if [ ! -f "db/prod-points.sqlite" ]; then
    print_status "Downloading production database..."
    curl -o db/prod-points.sqlite https://hitchmap.com/dump.sqlite
    print_success "Production database downloaded"
fi

# Set environment variables
export FLASK_APP=hitch
export FLASK_ENV=development
export ENVIRONMENT=dev

# Install and compile TypeScript if Node.js is available
if command_exists node; then
    print_status "Installing TypeScript dependencies..."
    cd hitch/scripts/fetch_hitchhiking_events
    if [ -f "package.json" ]; then
        npm install --silent
        print_status "Compiling TypeScript..."
        npx tsc
        print_success "TypeScript compilation complete"
    else
        print_warning "No package.json found in TypeScript directory"
    fi
    cd ../../..
fi

# Initialize database
print_status "Initializing database..."
flask init

# Function to watch for changes and rebuild
watch_files() {
    print_status "Starting file watcher..."
    
    # Determine which file watcher to use
    if command_exists fswatch; then
        # Use fswatch (macOS/BSD) - more efficient
        fswatch -o hitch/static/ hitch/templates/ hitch/scripts/fetch_hitchhiking_events/src/ hitch/*.py hitch/blueprints/ hitch/scripts/ | while read; do
            print_status "Files changed, regenerating map data..."
            flask generate show --no-heatmap --force
        done
    elif command_exists inotifywait; then
        # Use inotifywait (Linux)
        while true; do
            inotifywait -r -e modify,create,delete \
                hitch/static/ \
                hitch/templates/ \
                hitch/scripts/fetch_hitchhiking_events/src/ \
                hitch/*.py \
                hitch/blueprints/ \
                hitch/scripts/ \
                2>/dev/null || true
            print_status "Files changed, regenerating map data..."
            flask generate show --no-heatmap --force
        done
    else
        print_warning "No file watcher available. Install fswatch (macOS: brew install fswatch) or inotify-tools (Linux: apt-get install inotify-tools)"
        print_warning "Continuing without auto-reload..."
        return
    fi
}

# Start file watcher in background
watch_files &
WATCH_PID=$!

print_success "Development environment started!"
print_success "Flask server: http://localhost:4242"
print_success "File watching enabled for auto-reload"
print_status "Press Ctrl+C to stop all processes"

# Show logs
print_status "Starting Flask development server..."
flask run --host=0.0.0.0 --port=4242 --debug
