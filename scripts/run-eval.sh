#!/bin/bash

# Memo Evaluation Script

set -e

echo "🧪 Running Memo evaluation suite..."

# Check if backend is running
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo "❌ Backend is not running. Please start it first with:"
    echo "   ./scripts/start-dev.sh"
    exit 1
fi

cd eval

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing evaluation dependencies..."
    npm install
fi

echo "🎯 Running API endpoint tests..."
npx playwright test tests/api --reporter=line

echo "📊 Running scenario tests..."
npx playwright test tests/scenarios --reporter=line

echo "📈 Generating test report..."
npx playwright show-report --host 0.0.0.0 --port 9323 &
REPORT_PID=$!

echo ""
echo "✅ Evaluation complete!"
echo "📊 Test report available at http://localhost:9323"
echo ""
echo "Key metrics to check:"
echo "- All API tests should pass"
echo "- End-to-end latency < 2.5s"
echo "- Memory recall rate > 60%"
echo "- Job extraction accuracy > 80%"
echo ""

# Keep report server running
echo "Press Ctrl+C to stop the report server"
cleanup() {
    echo ""
    echo "🛑 Stopping report server..."
    kill $REPORT_PID 2>/dev/null || true
}

trap cleanup EXIT
wait $REPORT_PID