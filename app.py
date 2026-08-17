import os
import re
import unicodedata
from pathlib import Path

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request
from flask_cors import CORS
from openai import OpenAI


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VECTOR_STORE_ID = os.getenv("MINNESOTA_VECTOR_STORE_ID")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")

WHG_API_TOKEN = os.getenv("WHG_API_TOKEN")
WHG_RECONCILE_URL = os.getenv("WHG_RECONCILE_URL", "https://whgazetteer.org/reconcile")
WHG_USER_AGENT = os.getenv("WHG_USER_AGENT", "mn-gazetteer-app/0.1")


def read_int_env(name, default):
    value = os.getenv(name)
    if not value:
        return default

    try:
        return int(value)
    except ValueError:
        return default


MAX_MESSAGE_CHARS = read_int_env("MAX_MESSAGE_CHARS", 4000)
WHG_TIMEOUT_SECONDS = read_int_env("WHG_TIMEOUT_SECONDS", 12)
WHG_RESULT_LIMIT = read_int_env("WHG_RESULT_LIMIT", 5)

missing_settings = []
for setting_name in ("OPENAI_API_KEY", "MINNESOTA_VECTOR_STORE_ID"):
    if not os.getenv(setting_name):
        missing_settings.append(setting_name)

if missing_settings:
    missing = ", ".join(missing_settings)
    raise RuntimeError(f"Missing required environment setting(s): {missing}")

client = OpenAI(api_key=OPENAI_API_KEY)

with open(BASE_DIR / "prompt.txt", "r", encoding="utf-8") as prompt_file:
    SYSTEM_PROMPT = prompt_file.read()

app = Flask(__name__)
CORS(app)


INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Minnesota Gazetteer</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fa;
      --ink: #17211d;
      --muted: #5f6b65;
      --line: #d9dfdd;
      --panel: #ffffff;
      --field: #fbfcfd;
      --green: #214c3f;
      --teal: #2d7d87;
      --berry: #7b2f52;
      --gold: #b98228;
      --shadow: 0 18px 55px rgba(23, 33, 29, 0.10);
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(135deg, rgba(45, 125, 135, 0.10), transparent 34rem),
        linear-gradient(315deg, rgba(123, 47, 82, 0.08), transparent 28rem),
        var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    button,
    textarea {
      font: inherit;
    }

    .app {
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0;
    }

    .topbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
      margin-bottom: 18px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 14px;
      min-width: 0;
    }

    .mark {
      display: grid;
      width: 48px;
      height: 48px;
      border: 1px solid rgba(33, 76, 63, 0.34);
      border-radius: 8px;
      place-items: center;
      background:
        linear-gradient(90deg, transparent 46%, rgba(33, 76, 63, 0.16) 47%, rgba(33, 76, 63, 0.16) 53%, transparent 54%),
        linear-gradient(0deg, transparent 46%, rgba(45, 125, 135, 0.16) 47%, rgba(45, 125, 135, 0.16) 53%, transparent 54%),
        #ffffff;
      box-shadow: 0 10px 24px rgba(23, 33, 29, 0.08);
      color: var(--berry);
      font-weight: 800;
    }

    h1 {
      margin: 0;
      font-size: 1.45rem;
      line-height: 1.1;
      letter-spacing: 0;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 0.88rem;
      white-space: nowrap;
    }

    .status-dot {
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: var(--teal);
      box-shadow: 0 0 0 4px rgba(45, 125, 135, 0.14);
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(320px, 0.92fr) minmax(420px, 1.28fr);
      gap: 18px;
      align-items: start;
    }

    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.88);
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 58px;
      padding: 16px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.76);
    }

    .panel-title {
      margin: 0;
      font-size: 0.92rem;
      font-weight: 760;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #30423a;
    }

    form {
      display: grid;
      gap: 14px;
      padding: 18px;
    }

    textarea {
      width: 100%;
      min-height: 210px;
      resize: vertical;
      padding: 14px;
      border: 1px solid #cbd4d1;
      border-radius: 8px;
      background: var(--field);
      color: var(--ink);
      line-height: 1.5;
      outline: none;
    }

    textarea:focus {
      border-color: var(--teal);
      box-shadow: 0 0 0 3px rgba(45, 125, 135, 0.16);
    }

    .actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }

    .meta {
      color: var(--muted);
      font-size: 0.88rem;
    }

    .submit {
      min-width: 132px;
      border: 0;
      border-radius: 8px;
      background: var(--green);
      color: #ffffff;
      cursor: pointer;
      font-weight: 720;
      padding: 11px 16px;
    }

    .submit:hover {
      background: #183a30;
    }

    .submit:disabled {
      cursor: wait;
      opacity: 0.72;
    }

    .answer {
      min-height: 438px;
      padding: 20px;
      line-height: 1.62;
      white-space: pre-wrap;
    }

    .answer.empty {
      color: var(--muted);
    }

    .side-stack {
      display: grid;
      gap: 18px;
    }

    .place-list {
      display: grid;
      gap: 10px;
      padding: 16px 18px 18px;
    }

    .place-item {
      border-left: 4px solid var(--gold);
      padding: 8px 0 8px 12px;
    }

    .place-name {
      font-weight: 760;
    }

    .place-detail {
      margin-top: 3px;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.45;
    }

    .error {
      color: #9b1c31;
      font-weight: 650;
    }

    @media (max-width: 840px) {
      .app {
        width: min(100vw - 22px, 720px);
        padding: 18px 0;
      }

      .topbar {
        align-items: flex-start;
        flex-direction: column;
      }

      .layout {
        grid-template-columns: 1fr;
      }

      textarea {
        min-height: 180px;
      }

      .answer {
        min-height: 260px;
      }
    }
  </style>
</head>
<body>
  <main class="app">
    <header class="topbar">
      <div class="brand">
        <div class="mark" aria-hidden="true">MN</div>
        <h1>Minnesota Gazetteer</h1>
      </div>
      <div class="status" data-status>
        <span class="status-dot" aria-hidden="true"></span>
        <span>Ready</span>
      </div>
    </header>

    <section class="layout">
      <div class="side-stack">
        <section class="panel">
          <div class="panel-header">
            <p class="panel-title">Query</p>
          </div>
          <form data-form>
            <textarea data-message spellcheck="true">Tell me about Mankato in the 1850s.</textarea>
            <div class="actions">
              <span class="meta" data-counter>0 characters</span>
              <button class="submit" type="submit" data-submit>Ask</button>
            </div>
          </form>
        </section>

        <section class="panel">
          <div class="panel-header">
            <p class="panel-title">WHG Candidates</p>
          </div>
          <div class="place-list" data-places>
            <div class="meta">No query yet.</div>
          </div>
        </section>
      </div>

      <section class="panel">
        <div class="panel-header">
          <p class="panel-title">Answer</p>
        </div>
        <div class="answer empty" data-answer>Submit a query to begin.</div>
      </section>
    </section>
  </main>

  <script>
    const form = document.querySelector("[data-form]");
    const message = document.querySelector("[data-message]");
    const answer = document.querySelector("[data-answer]");
    const places = document.querySelector("[data-places]");
    const statusLabel = document.querySelector("[data-status] span:last-child");
    const submit = document.querySelector("[data-submit]");
    const counter = document.querySelector("[data-counter]");

    function setStatus(text) {
      statusLabel.textContent = text;
    }

    function updateCounter() {
      const count = message.value.length;
      counter.textContent = count + " characters";
    }

    function clearNode(node) {
      while (node.firstChild) {
        node.removeChild(node.firstChild);
      }
    }

    function renderPlaces(items, note) {
      clearNode(places);

      if (!items || items.length === 0) {
        const empty = document.createElement("div");
        empty.className = "meta";
        empty.textContent = note || "No candidates returned.";
        places.appendChild(empty);
        return;
      }

      for (let index = 0; index < items.length; index += 1) {
        const item = items[index];
        const wrapper = document.createElement("div");
        wrapper.className = "place-item";

        const name = document.createElement("div");
        name.className = "place-name";
        name.textContent = item.name || "Unnamed place";
        wrapper.appendChild(name);

        const detail = document.createElement("div");
        detail.className = "place-detail";

        let pieces = [];
        if (item.id) {
          pieces.push(item.id);
        }
        if (item.namespace) {
          pieces.push("source: " + item.namespace);
        }
        if (item.score !== null && item.score !== undefined) {
          pieces.push("score: " + item.score);
        }
        if (item.description) {
          pieces.push(item.description);
        }

        detail.textContent = pieces.join(" | ");
        wrapper.appendChild(detail);
        places.appendChild(wrapper);
      }
    }

    async function askGazetteer(event) {
      event.preventDefault();

      const text = message.value.trim();
      if (!text) {
        answer.className = "answer error";
        answer.textContent = "A query is required.";
        return;
      }

      submit.disabled = true;
      answer.className = "answer empty";
      answer.textContent = "Working...";
      setStatus("Retrieving");
      renderPlaces([], "");

      try {
        const response = await fetch("/api/gazetteer", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            message: text
          })
        });

        const payload = await response.json();

        if (!response.ok) {
          const errorText = payload.error || "Unable to generate a response.";
          throw new Error(errorText);
        }

        answer.className = "answer";
        answer.textContent = payload.text || "";
        renderPlaces(payload.places || [], payload.whg_note || "");
        setStatus("Ready");
      } catch (error) {
        answer.className = "answer error";
        answer.textContent = error.message;
        setStatus("Error");
      } finally {
        submit.disabled = false;
      }
    }

    message.addEventListener("input", updateCounter);
    form.addEventListener("submit", askGazetteer);
    updateCounter();
  </script>
</body>
</html>
"""


def add_unique_candidate(candidates, value):
    clean = re.sub(r"\s+", " ", value).strip(" .,;:!?()[]{}\"'")
    if not clean:
        return

    lowered = clean.lower()
    skip_values = {
        "a",
        "an",
        "and",
        "are",
        "did",
        "does",
        "how",
        "in",
        "is",
        "it",
        "me",
        "minnesota",
        "mn",
        "of",
        "or",
        "tell",
        "the",
        "what",
        "when",
        "where",
        "who",
        "why",
    }
    if lowered in skip_values:
        return

    for existing in candidates:
        if existing.lower() == lowered:
            return

    candidates.append(clean)


def build_place_queries(message):
    candidates = []
    normalized = re.sub(r"\s+", " ", message).strip()

    if normalized and len(normalized) <= 90:
        add_unique_candidate(candidates, normalized)

    preposition_pattern = re.compile(
        r"\b(?:about|along|around|at|between|from|in|near|of|through|to)\s+"
        r"([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,3})",
        re.UNICODE,
    )
    title_pattern = re.compile(
        r"\b([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,3})\b",
        re.UNICODE,
    )

    for match in preposition_pattern.finditer(message):
        add_unique_candidate(candidates, match.group(1))

    for match in title_pattern.finditer(message):
        add_unique_candidate(candidates, match.group(1))

    if not candidates and normalized:
        add_unique_candidate(candidates, normalized[:90])

    return candidates[:6]


def normalize_alt_names(value):
    names = []
    if not value:
        return names

    for item in value:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            for key in ("toponym", "name", "label"):
                text = item.get(key)
                if text:
                    names.append(text)
                    break

        if len(names) >= 5:
            break

    return names


def normalize_whg_candidate(query_text, candidate):
    alt_names = normalize_alt_names(candidate.get("alt_names"))
    normalized = {
        "query": query_text,
        "id": candidate.get("id"),
        "name": candidate.get("name"),
        "score": candidate.get("score"),
        "match": candidate.get("match"),
        "description": candidate.get("description"),
        "namespace": candidate.get("namespace"),
        "has_geom": candidate.get("has_geom"),
        "alt_names": alt_names,
    }
    return normalized


def normalize_match_text(value):
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def extract_match_tokens(value):
    tokens = []
    normalized = normalize_match_text(value)
    for token in normalized.split():
        if len(token) < 3:
            continue
        if token in ("about", "tell", "what", "when", "where", "which", "with"):
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def whg_candidate_resembles_query(query_text, candidate):
    if candidate.get("match") is True:
        return True

    query_normalized = normalize_match_text(query_text)
    name_normalized = normalize_match_text(candidate.get("name", ""))
    if query_normalized and name_normalized:
        if query_normalized in name_normalized:
            return True
        if name_normalized in query_normalized:
            return True

    query_tokens = extract_match_tokens(query_text)
    candidate_texts = [candidate.get("name", "")]
    alt_names = candidate.get("alt_names") or []
    for alt_name in alt_names:
        if isinstance(alt_name, str):
            candidate_texts.append(alt_name)
        elif isinstance(alt_name, dict):
            for key in ("toponym", "name", "label"):
                value = alt_name.get(key)
                if value:
                    candidate_texts.append(value)
                    break

    for candidate_text in candidate_texts:
        candidate_tokens = extract_match_tokens(candidate_text)
        for query_token in query_tokens:
            if query_token in candidate_tokens:
                return True

    return False


def build_whg_request_queries(place_queries, profile):
    request_queries = {}
    key_to_query = {}

    index = 0
    for place_query in place_queries:
        key = f"q{index}"
        key_to_query[key] = place_query

        query = {
            "query": place_query,
            "mode": profile.get("mode", "fuzzy"),
            "undated": True,
            "limit": WHG_RESULT_LIMIT,
        }

        countries = profile.get("countries")
        if countries:
            query["countries"] = countries

        namespaces = profile.get("namespaces")
        if namespaces:
            query["namespaces"] = namespaces

        fclasses = profile.get("fclasses")
        if fclasses:
            query["fclasses"] = fclasses

        request_queries[key] = query
        index += 1

    return request_queries, key_to_query


def extract_whg_query_results(payload, key_to_query):
    query_results = payload.get("queries")
    if not query_results:
        query_results = {}
        for key in key_to_query:
            query_payload = payload.get(key)
            if query_payload:
                query_results[key] = query_payload

    return query_results


def collect_whg_places(payload, key_to_query):
    places = []
    seen = set()
    query_results = extract_whg_query_results(payload, key_to_query)

    for key in key_to_query:
        query_payload = query_results.get(key, {})
        query_text = key_to_query.get(key, key)
        result_items = query_payload.get("result", [])

        for candidate in result_items:
            if not whg_candidate_resembles_query(query_text, candidate):
                continue

            normalized = normalize_whg_candidate(query_text, candidate)
            identity = normalized.get("id") or f"{normalized.get('name')}|{normalized.get('namespace')}"
            if identity in seen:
                continue

            seen.add(identity)
            places.append(normalized)
            if len(places) >= 12:
                return places

    return places


def post_whg_reconciliation(place_queries, profile, headers):
    request_queries, key_to_query = build_whg_request_queries(place_queries, profile)
    response = requests.post(
        WHG_RECONCILE_URL,
        json={"queries": request_queries},
        headers=headers,
        timeout=WHG_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    payload = response.json()
    places = collect_whg_places(payload, key_to_query)
    return payload, places


def reconcile_with_whg(place_queries):
    if not WHG_API_TOKEN:
        return {
            "enabled": False,
            "note": "WHG was not queried because WHG_API_TOKEN is not set.",
            "places": [],
            "attribution": {},
        }

    if not place_queries:
        return {
            "enabled": True,
            "note": "No candidate place names were detected for WHG reconciliation.",
            "places": [],
            "attribution": {},
        }

    headers = {
        "Authorization": f"Bearer {WHG_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": WHG_USER_AGENT,
    }

    profiles = [
        {
            "name": "exact_us_core",
            "mode": "exact",
            "countries": ["US"],
            "namespaces": "whg,gn,tgn",
        },
        {
            "name": "fuzzy_us_core",
            "mode": "fuzzy",
            "countries": ["US"],
            "namespaces": "whg,gn,tgn",
        },
        {
            "name": "fuzzy_us_all_sources",
            "mode": "fuzzy",
            "countries": ["US"],
        },
        {
            "name": "fuzzy_core_no_country",
            "mode": "fuzzy",
            "namespaces": "whg,gn,tgn",
        },
    ]

    payload = {}
    places = []
    profile_used = ""
    for profile in profiles:
        payload, places = post_whg_reconciliation(place_queries, profile, headers)
        profile_used = profile.get("name", "")
        if places:
            break

    return {
        "enabled": True,
        "note": "" if places else "WHG returned no candidates after focused and fallback reconciliation attempts.",
        "places": places,
        "profile": profile_used,
        "attribution": payload.get("attribution", {}),
    }


def format_whg_context(whg_payload):
    if not whg_payload.get("enabled"):
        return whg_payload.get("note", "WHG was not queried.")

    places = whg_payload.get("places", [])
    if not places:
        note = whg_payload.get("note")
        if note:
            return note
        return "WHG returned no candidates."

    lines = ["WHG place-resolution candidates:"]
    for place in places:
        detail_parts = []
        for key in ("id", "namespace", "score", "description"):
            value = place.get(key)
            if value is not None and value != "":
                detail_parts.append(f"{key}={value}")

        if place.get("match") is not None:
            detail_parts.append(f"match={place.get('match')}")

        alt_names = place.get("alt_names", [])
        if alt_names:
            detail_parts.append("alt_names=" + ", ".join(alt_names))

        details = "; ".join(detail_parts)
        lines.append(f"- query={place.get('query')}: {place.get('name')} ({details})")

    return "\n".join(lines)


def build_model_input(message, whg_context):
    return (
        "User question:\n"
        f"{message}\n\n"
        "WHG place-resolution context:\n"
        f"{whg_context}\n\n"
        "Use WHG for place identity, names, coordinates, types, temporal hints, and disambiguation. "
        "Use the Minnesota Gazetteer vector store for Minnesota-specific historical and interpretive evidence. "
        "If WHG context is absent or ambiguous, say so when it affects the answer."
    )


def extract_file_citations(response):
    citations = []
    output_items = getattr(response, "output", None)
    if not output_items:
        return citations

    for output_item in output_items:
        if getattr(output_item, "type", None) != "message":
            continue

        content_items = getattr(output_item, "content", None)
        if not content_items:
            continue

        for content_item in content_items:
            annotations = getattr(content_item, "annotations", None)
            if not annotations:
                continue

            for annotation in annotations:
                if getattr(annotation, "type", None) != "file_citation":
                    continue

                citation = {
                    "file_id": getattr(annotation, "file_id", None),
                    "filename": getattr(annotation, "filename", None),
                    "index": getattr(annotation, "index", None),
                }
                citations.append(citation)

    return citations


@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)


@app.route("/health", methods=["GET"])
def health():
    return jsonify(
        {
            "status": "ok",
            "service": "Minnesota Gazetteer",
            "model": OPENAI_MODEL,
            "whg_enabled": bool(WHG_API_TOKEN),
        }
    )


@app.route("/api/gazetteer", methods=["POST"])
def gazetteer():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({"error": "A message is required."}), 400

    if len(message) > MAX_MESSAGE_CHARS:
        return jsonify({"error": f"Message must be {MAX_MESSAGE_CHARS} characters or fewer."}), 400

    place_queries = build_place_queries(message)

    try:
        whg_payload = reconcile_with_whg(place_queries)
    except requests.RequestException as error:
        whg_payload = {
            "enabled": bool(WHG_API_TOKEN),
            "note": f"WHG lookup failed: {error}",
            "places": [],
            "attribution": {},
        }

    whg_context = format_whg_context(whg_payload)
    model_input = build_model_input(message, whg_context)

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_PROMPT,
            input=model_input,
            include=["file_search_call.results"],
            tools=[
                {
                    "type": "file_search",
                    "vector_store_ids": [VECTOR_STORE_ID],
                    "max_num_results": 20,
                }
            ],
        )
    except Exception as error:
        app.logger.exception("OpenAI request failed")
        return jsonify({"error": f"OpenAI request failed: {error}"}), 500

    return jsonify(
        {
            "text": response.output_text,
            "response_id": response.id,
            "model": OPENAI_MODEL,
            "places": whg_payload.get("places", []),
            "whg_enabled": whg_payload.get("enabled", False),
            "whg_note": whg_payload.get("note", ""),
            "file_citations": extract_file_citations(response),
        }
    )


if __name__ == "__main__":
    port = read_int_env("PORT", 5000)
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
