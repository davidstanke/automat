import logging
import os
import io
import pypdf
from dotenv import load_dotenv
from google.cloud import storage

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models.google_llm import Gemini
from google.genai.types import HttpRetryOptions, ThinkingConfig, ThinkingLevel

# Load environment variables
# override=True: a stale shell export must not beat .env.
load_dotenv(override=True)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"


# In-memory document cache to eliminate multi-second pypdf overhead on every invocation
_DOCUMENT_CACHE: dict[str, str] = {}


def load_and_cache_strategy_documents(force_refresh: bool = False) -> str:
    """Loads and caches strategy document text in memory.

    Pre-parsing documents at container initialization provides instant (<1ms)
    retrieval during agent execution cycles and trims redundant boilerplate.
    """
    global _DOCUMENT_CACHE
    if not force_refresh and "content" in _DOCUMENT_CACHE:
        return _DOCUMENT_CACHE["content"]

    bucket_name = os.getenv("STRATEGY_DOCS_BUCKET")
    extracted_texts = []

    if bucket_name:
        print(f"[Strategy Agent] Pre-caching GCS bucket: '{bucket_name}'...")
        try:
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blobs = list(bucket.list_blobs())
        except Exception as e:
            raise RuntimeError(
                f"Cannot read STRATEGY_DOCS_BUCKET '{bucket_name}': {e}. Needs"
                " roles/storage.objectViewer for this agent's service account."
            ) from e

        pdf_blobs = [b for b in blobs if b.name.lower().endswith(".pdf")]
        if not pdf_blobs:
            raise RuntimeError(
                f"STRATEGY_DOCS_BUCKET '{bucket_name}' contains no PDFs. Upload them,"
                " or unset the variable to use the copies in data/docs/."
            )

        for blob in pdf_blobs:
            pdf_data = blob.download_as_bytes()
            pdf_reader = pypdf.PdfReader(io.BytesIO(pdf_data))
            text = "".join(page.extract_text() or "" for page in pdf_reader.pages)
            extracted_texts.append(f"--- Document (GCS): {blob.name} ---\n{text.strip()}\n")
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        strat_agent_dir = os.path.dirname(current_dir)
        local_docs_dir = os.path.join(strat_agent_dir, "data", "docs")
        if not os.path.exists(local_docs_dir):
            local_docs_dir = os.path.join(strat_agent_dir, "data")

        print(f"[Strategy Agent] Pre-caching local docs from: '{local_docs_dir}'...")
        if not os.path.exists(local_docs_dir):
            return f"Local strategy documents directory not found at '{local_docs_dir}'."

        try:
            pdf_files = [f for f in os.listdir(local_docs_dir) if f.lower().endswith(".pdf")]
        except Exception as e:
            return f"Error listing local directory '{local_docs_dir}': {str(e)}"

        if not pdf_files:
            return f"No PDF documents found in local directory '{local_docs_dir}'."

        for file_name in pdf_files:
            file_path = os.path.join(local_docs_dir, file_name)
            try:
                pdf_reader = pypdf.PdfReader(file_path)
                text = "".join(page.extract_text() or "" for page in pdf_reader.pages)
                extracted_texts.append(f"--- Document (Local): {file_name} ---\n{text.strip()}\n")
            except Exception as e:
                extracted_texts.append(f"--- Document (Local): {file_name} ---\nError parsing PDF: {str(e)}\n")

    content = "\n\n".join(extracted_texts)
    _DOCUMENT_CACHE["content"] = content
    return content


def inspect_strategy_documents() -> str:
    """Returns extracted corporate strategy documents instantly from in-memory cache."""
    return load_and_cache_strategy_documents()


strat_retry_policy = HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=30.0,
    http_status_codes=[429, 500, 503],
)

logger = logging.getLogger(__name__)

MODEL_LOCATION = os.getenv("GOOGLE_GENAI_LOCATION", "global")
# Pinned version. Override via GOOGLE_GENAI_MODEL. Served from global endpoint.
MODEL = os.getenv("GOOGLE_GENAI_MODEL", "gemini-3.7-flash")

# Pre-warm document cache on module load if local files exist
try:
    load_and_cache_strategy_documents()
except Exception as _e:
    logger.warning("Could not pre-warm strategy documents cache on startup: %s", _e)

logger.info("Using Gemini model '%s' in location '%s'", MODEL, MODEL_LOCATION)

root_agent = Agent(
    model=Gemini(
        model=MODEL,
        thinking_config=ThinkingConfig(thinking_level=ThinkingLevel.MINIMAL),
        retry_options=strat_retry_policy,
        client_kwargs={"location": MODEL_LOCATION},
    ),
    name="strategy_agent",
    description="Analyzes corporate strategy documents and returns a brief strategic summary.",
    instruction=(
        "You are an expert strategic analyst for GeniCo. Your task is to analyze the text "
        "provided by the 'inspect_strategy_documents' tool and summarize the corporate strategy "
        "and key product initiatives (especially flagship launches such as OmniChef) implied by those documents.\n\n"
        "Always call the 'inspect_strategy_documents' tool first to retrieve the facts and provide the strategic context, "
        "even when the user prompt relates to scheduling, team gatherings, or events (which are aligned with company initiatives).\n\n"
        "Rules for your output:\n"
        "1. Structure your output with clear Markdown headers, including '## Strategic Priorities & Key Initiatives' and '## Strategic Context'.\n"
        "2. Always explicitly highlight major active product launches and strategic projects (e.g., OmniChef Global Launch, VisionSphere).\n"
        "3. Keep your summary concise, high-density, and structured with bullet points (under 200 words total). Avoid long discursive background paragraphs to enable fast downstream synthesis.\n"
        "4. Do not assume or hallucinate outside the contents of the provided documents.\n"
        "5. You must call the 'inspect_strategy_documents' tool first to retrieve the facts."
    ),
    tools=[inspect_strategy_documents],
)

app = App(
    root_agent=root_agent,
    name="app",
)

