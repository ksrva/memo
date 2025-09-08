#!/bin/bash

# Memo Development Startup Script

set -e

echo "🚀 Starting Memo development environment..."

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

# Check if Node.js is available  
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is required but not installed"
    exit 1
fi

# Check if OpenAI API key is set
if [ ! -f backend/.env ]; then
    echo "⚠️  Creating .env file from example..."
    cp backend/.env.example backend/.env
    echo "📝 Please edit backend/.env and add your OpenAI API key"
    echo "   Then run this script again."
    exit 1
fi

# Function to check if port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null ; then
        echo "❌ Port $1 is already in use"
        exit 1
    fi
}

# Check ports
check_port 8000

echo "📦 Installing backend dependencies..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt

echo "🛠️  Installing NLTK data..."
python -c "import nltk; nltk.download('punkt', quiet=True)"

echo "🗄️  Initializing database..."
python -c "from app.database import Database; Database()"

echo "🌐 Starting FastAPI server..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

cd ../

echo "📱 Building Chrome extension..."
cd extension
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run build

cd ../

# Wait for backend to start
echo "⏳ Waiting for backend to start..."
sleep 3

# Check if backend is running
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ Backend is running at http://localhost:8000"
    echo "📖 API docs available at http://localhost:8000/docs"
else
    echo "❌ Backend failed to start"
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
fi

echo ""
echo "🎉 Memo development environment is ready!"
echo ""
echo "Next steps:"
echo "1. Load the Chrome extension from extension/dist/"
echo "2. Visit any webpage and click the Memo button"
echo "3. Run tests with: cd eval && npm test"
echo ""
echo "Press Ctrl+C to stop all services"

# Keep script running and handle cleanup
cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $BACKEND_PID 2>/dev/null || true
    echo "✅ Cleanup complete"
}

trap cleanup EXIT
wait