#!/bin/bash

# BarberScore POS - Quick Start Script
# Starts both API and UI in one command

echo "================================================"
echo "  BarberScore POS - Starting Local Environment"
echo "================================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ No .env file found!"
    echo ""
    echo "Please run setup first:"
    echo "  ./setup-local.sh"
    echo ""
    echo "Or see LOCAL_SETUP.md for manual setup."
    exit 1
fi

# Check if dependencies are installed
if ! command -v uvicorn &> /dev/null; then
    echo "📦 Installing Python dependencies..."
    pip install -r requirements.txt
fi

echo "🚀 Starting services..."
echo ""
echo "  API:  http://localhost:8000"
echo "  Docs: http://localhost:8000/docs"
echo "  UI:   http://localhost:8080/app.html"
echo ""
echo "Press Ctrl+C to stop"
echo ""
echo "================================================"
echo ""

# Start API in background
echo "Starting API server..."
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait a moment for API to start
sleep 2

# Start UI server in background
echo "Starting UI server..."
cd web
python -m http.server 8080 &
UI_PID=$!

# Go back to root
cd ..

echo ""
echo "✅ Services started!"
echo ""
echo "Next steps:"
echo "  1. Open: http://localhost:8080/app.html"
echo "  2. Register a new account"
echo "  3. Start processing sales!"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for user interrupt
trap "echo ''; echo 'Stopping services...'; kill $API_PID $UI_PID 2>/dev/null; exit 0" INT

# Keep script running
wait
