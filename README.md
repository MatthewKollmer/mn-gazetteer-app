# Minnesota Gazetteer App

A small Flask web app backed by the OpenAI Responses API, my Minnesota/semantic layer vector store, and the World Historical Gazetteer place reconciliation.

This is just an early prototype. More details about this project will be added soon.

This prototype has been configured in part using Codex.

## Local Setup

Create or update `.env` in this folder:

```text
OPENAI_API_KEY=your_openai_api_key
MINNESOTA_VECTOR_STORE_ID=your_vector_store_id
OPENAI_MODEL=gpt-5.6
WHG_API_TOKEN=your_whg_api_token
```

`WHG_API_TOKEN` is optional for local testing, but the app will only perform WHG place resolution when it is present.

Install and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## API

Health check:

```bash
curl http://127.0.0.1:5000/health
```

Ask a question:

```bash
curl -X POST http://127.0.0.1:5000/api/gazetteer \
  -H "Content-Type: application/json" \
  -d '{"message":"Tell me about Mankato in the 1850s."}'
```

## Deployment Notes

The app reads `PORT`, `OPENAI_MODEL`, `MAX_MESSAGE_CHARS`, `WHG_TIMEOUT_SECONDS`, `GUNICORN_TIMEOUT`, and `FLASK_DEBUG` from the environment. `GUNICORN_TIMEOUT` defaults to 120 seconds so longer multi-place requests can finish. For Render, Railway, Fly, or a similar host, set the same environment variables there and use:

```bash
gunicorn -c gunicorn_config.py app:app
```

For DigitalOcean App Platform, use the same run command. The included
`gunicorn_config.py` binds Gunicorn to `0.0.0.0:$PORT` and uses `/dev/shm` for
worker temp files.

Keep `.env` out of Git.
