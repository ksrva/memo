# Memo

A Chrome extension for taking notes on articles. Highlight a passage, write your
notes, save. You can search your notes later, and when you open a page related to
something you saved before, Memo shows you that note.

Notes are stored in a file on your computer. No account, no sign-up.

## What you need

- **Python 3.10 or newer** — check with `python3 --version`
- **Node.js 18 or newer** — check with `node --version`
- **Google Chrome**

## Try it out

Three steps, about two minutes.

### 1. Get the code

```bash
git clone <your-repo-url> memo
cd memo
```

### 2. Start the server

```bash
./scripts/start-dev.sh
```

The first run creates a virtual environment and installs dependencies, so it takes
a minute. After that it starts in a second or two.

Leave this running. The extension talks to it.

You should see:

```
INFO:memo:Memo ready — 0 notes in store
INFO:     Uvicorn running on http://127.0.0.1:8000
```

If port 8000 is already used by something else, pick another one:

```bash
PORT=8001 ./scripts/start-dev.sh
```

Then set the same address in the extension later (see Settings below).

### 3. Build and load the extension

In a second terminal:

```bash
cd memo/extension
npm install
npm run build
```

Then in Chrome:

1. Go to `chrome://extensions`
2. Turn on **Developer mode** (top right)
3. Click **Load unpacked**
4. Select the folder `memo/extension/dist`

Pick the `dist` folder itself. Not the `memo` folder, and not `extension`. `dist`
is the only one with a `manifest.json` in it.

## Using it

1. Open any article.
2. Select some text.
3. Click the Memo icon in your toolbar. The side panel opens.
4. Your selected text shows up under **Passage**. If it doesn't, click
   **Use highlighted**.
5. Type your notes in the box. **Save note** turns on once you've written
   something.
6. Click **Save note**, or press `Cmd+Enter`.

Notes are required. Memo won't save a highlight without them.

To find things later, use the **Search** tab. **Recent** shows everything you've
saved.

## Better search (optional)

Out of the box, search matches words. Search for "funny" and you'll find notes
with the word "funny" in them. Search for "amusing" and you won't.

To search by meaning instead, add one of these. Both are optional.

### Ollama — free, runs on your computer

```bash
brew install ollama
ollama serve                    # leave running, or: brew services start ollama
ollama pull nomic-embed-text    # 275 MB, downloads once
```

Restart the Memo server. Nothing gets sent over the internet.

### OpenAI — needs a paid account

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and add your key:

```
OPENAI_API_KEY=sk-...
```

Restart the Memo server. Editing `.env` while it's running does nothing, you have
to restart.

This also fills in tags and a one-line summary of each passage.

### Checking it worked

```bash
curl -s localhost:8000/v1/health
```

Look for `"search":"semantic"`. If it says `"state":"error"`, the key or the
connection is wrong and the message will tell you which.

Notes you saved before adding this won't be searchable by meaning. Only new ones
will. If you've only saved a few, the simplest fix is to delete `backend/memo.db`
and start over.

## Settings

Open the side panel and click **Server address** at the top. Use this if you
started the server on a port other than 8000.

## If something goes wrong

**The panel says it can't reach the server.** The server isn't running, or it's on
a different port. Check the terminal where you ran `start-dev.sh`, and check the
address under **Server address**.

**"Manifest file is missing or unreadable" when loading the extension.** You picked
the wrong folder. It has to be `memo/extension/dist`.

**Your selected text doesn't show up.** Click **Use highlighted**. If that doesn't
work, reload the page and try again.

**You changed something and nothing happened.** Go to `chrome://extensions` and
click the reload arrow on the Memo card. Closing and reopening the panel isn't
always enough.

## Where your notes are

Everything lives in one file: `backend/memo.db`. Notes, search index, and
embeddings. Copy that file to back up; delete it to start over.

## Running the tests

```bash
cd backend
.venv/bin/pytest -q
```

29 tests. No API key needed, no internet.

## License

MIT
