# 🏢 GeniCo PDF Corpus Maker

This utility generates a high-quality, professional corporate document corpus (PDF format) for the fictional company **GeniCo** using **Gemini 2.5 Flash** and **ReportLab**.

## 🚀 Setup & Execution

1. **Configure Authentication**. The utility supports two methods:

   * **Option A: Standard Gemini API Key** (Add to the `.env` file in the project root):
     ```env
     GEMINI_API_KEY="your_api_key_here"
     ```
   * **Option B: Google Cloud Application Default Credentials (ADC)** (Add GCP variables to `.env` and authenticate your terminal):
     ```env
     GOOGLE_CLOUD_PROJECT_ID="your_gcp_project_id"
     GOOGLE_CLOUD_LOCATION="us-central1"
     ```
     Ensure you are authenticated:
     ```bash
     gcloud auth application-default login
     ```

2. **Run the orchestrator**:

   * **Option A: Using `uv` (Recommended - Zero Installation Needed)**:
     If you have `uv` installed, you can execute the utility directly. `uv` will automatically read the inline script metadata, set up an isolated environment, and run the script with all dependencies in seconds:
     ```bash
     uv run run.py
     ```
   
   * **Option B: Using standard Python**:
     The script will automatically detect if `uv` is available on your system to install missing packages ultra-fast, or fall back to standard `pip` if not:
     ```bash
     ./run.py
     ```

## 🛠️ Advanced Usage

The generation is split into two steps: creating a manifest blueprint of 15 documents, and then compiling those documents with inline charts and structured copy.

- **Only generate the JSON blueprint**:
  ```bash
  ./run.py --manifest-only
  ```
- **Only compile PDFs using an existing blueprint**:
  ```bash
  ./run.py --pdfs-only
  ```
- **Force regenerate blueprint and compile PDFs**:
  ```bash
  ./run.py --force-new-manifest
  ```

Generated PDFs are saved inside `agents/strat_agent/data/docs/`.
