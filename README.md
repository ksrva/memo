# Memo - Context-Aware Memory & Summarization API

A browser-native assistant that captures page context, stores searchable memories, and generates structured memos.

## Architecture

- **Backend**: FastAPI + SQLite + Vector Search
- **Frontend**: Chrome Extension (MV3, TypeScript) 
- **LLM**: OpenAI GPT-4 + Embeddings
- **Storage**: SQLite with sqlite-vss for vector search
- **Eval**: Playwright automation testing

## Features
**Context Capture**: Page text, title, URL, selections, recent clicks  
**Smart Memos**: AI-generated summaries with entities, tasks, and risks  
**Memory Store**: Searchable past memos with semantic similarity  
**REST API**: Clean endpoints for external integrations  
**Chrome Extension**: One-click memo creation with side panel UI  

## Prerequisites

- **Python**: 3.8 or higher
- **Node.js**: 16.0 or higher  
- **Chrome Browser**: Latest version
- **OpenAI API Key**: Required for LLM functionality

## Setup Instructions

### 1. Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key: OPENAI_API_KEY=sk-...

# Start the server
python -m app.main
```

The backend will start on http://localhost:8000

### 2. Extension Setup
```bash
cd extension

# Install dependencies
npm install

# Build the extension
npm run build
```

**Load Extension in Chrome:**
1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (top right toggle)
3. Click "Load unpacked" 
4. Select the `extension/dist/` folder
5. The Memo extension should appear in your toolbar

### 3. Testing the Setup
```bash
cd eval

# Install test dependencies  
npm install

# Run end-to-end tests
npx playwright test
```

**Manual Testing:**
1. Navigate to any webpage
2. Click the Memo extension icon
3. Click "Create Memo" to generate a summary
4. View saved memos in the side panel

## API Endpoints

| Endpoint | Method | Description |
|----------|---------|-------------|
| `/v1/compose` | POST | Build context bundle from page data |
| `/v1/summarize` | POST | Generate structured memo |
| `/v1/memory/upsert` | POST | Save memo to memory store |
| `/v1/memory/search` | GET | Search past memos |
| `/v1/metrics` | GET | Prometheus metrics |

## Project Structure

```
memo/
├── backend/          # FastAPI server
│   ├── app/         # Application code
│   ├── requirements.txt
│   └── .env.example
├── extension/       # Chrome Extension
│   ├── src/        # TypeScript source
│   ├── public/     # Manifest and assets
│   └── dist/       # Built extension
├── eval/           # Playwright tests
└── README.md
```

## Troubleshooting

**Backend Issues:**
- Ensure Python 3.8+ is installed: `python --version`
- Virtual environment activated before installing packages
- OpenAI API key is valid and has credits

**Extension Issues:**
- Clear Chrome extension errors in `chrome://extensions/`
- Reload extension after code changes
- Check browser console for JavaScript errors

**Database Issues:**
- SQLite database auto-creates on first run
- Check `memo_db.sqlite` file exists in backend folder

