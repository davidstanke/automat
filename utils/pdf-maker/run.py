#!/usr/bin/env python3
# /// script
# dependencies = [
#   "google-genai",
#   "reportlab",
#   "matplotlib",
#   "python-dotenv",
# ]
# ///
"""
GeniCo Document Corpus Generator - Unified Orchestrator Wrapper
This script handles dependency validation, environment setup, and sequential execution
of the manifest generation and PDF compilation.
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path

# Paths setup
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
MANIFEST_PATH = CURRENT_DIR / "manifests" / "docs_manifest.json"

# List of required external packages mapped to imports
REQUIRED_PACKAGES = {
    "google-genai": "google.genai",
    "reportlab": "reportlab",
    "matplotlib": "matplotlib",
    "python-dotenv": "dotenv"
}

def install_dependencies():
    """Attempt to install required packages via uv or pip."""
    print("📦 Installing missing dependencies from requirements.txt...")
    req_file = CURRENT_DIR / "requirements.txt"
    has_uv = shutil.which("uv") is not None
    try:
        if has_uv:
            print("⚡ 'uv' detected! Installing dependencies with uv for maximum speed...")
            subprocess.check_call(["uv", "pip", "install", "-r", str(req_file)])
        else:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
        print("✅ Dependencies successfully installed!\n")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies. Please run 'pip install -r requirements.txt' manually. Error: {e}")
        sys.exit(1)


def check_and_bootstrap_dependencies():
    """Check if all required packages are present, and install them if missing."""
    import importlib.util
    
    missing_packages = []
    for pkg_name, import_name in REQUIRED_PACKAGES.items():
        if importlib.util.find_spec(import_name) is None:
            missing_packages.append(pkg_name)
            
    if missing_packages:
        print(f"⚠️ Missing packages: {', '.join(missing_packages)}")
        # Auto install since user opted for wrapper managing dependencies
        install_dependencies()

def load_environment():
    """Ensure .env is loaded and credentials are configured."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT_DIR / ".env")
    except ImportError:
        pass # Will be installed by check_and_bootstrap_dependencies
        
    api_key = os.environ.get("GEMINI_API_KEY")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    
    if not api_key and not project_id:
        print("\n❌ Error: No authentication credentials found.")
        print("Please resolve this by either:")
        print("  1. Setting `GEMINI_API_KEY` in the root `.env` or your environment.")
        print("  2. Configuring Google Cloud Application Default Credentials (ADC) and setting `GOOGLE_CLOUD_PROJECT_ID` in the root `.env` or your environment.")
        print("\nGet a free API key from Google AI Studio: https://aistudio.google.com/")
        sys.exit(1)


def run_script(script_name):
    """Run a sub-script using the current interpreter."""
    script_path = CURRENT_DIR / script_name
    try:
        subprocess.check_call([sys.executable, str(script_path)])
    except subprocess.CalledProcessError as e:
        print(f"❌ Execution of {script_name} failed. Error: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        description="GeniCo Fictional Corporate Document Corpus Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                         # Generate manifest (if missing) and compile PDFs
  python run.py --force-new-manifest    # Regenerate manifest from scratch and compile PDFs
  python run.py --manifest-only         # Generate manifest and stop
  python run.py --pdfs-only             # Compile PDFs using existing manifest
"""
    )
    parser.add_argument("--manifest-only", action="store_true", help="Only run Step 1 (Manifest Generator)")
    parser.add_argument("--pdfs-only", action="store_true", help="Only run Step 2 (PDF Compiler) using existing manifest")
    parser.add_argument("--force-new-manifest", action="store_true", help="Force-regenerate the JSON manifest blueprint")
    
    args = parser.parse_args()
    
    print("======================================================================")
    print("          🏢 GeniCo Document Corpus Generator Wrapper 🏢")
    print("======================================================================")
    
    # 1. Self-heal dependencies
    check_and_bootstrap_dependencies()
    
    # 2. Check and load environment (Gemini Key)
    load_environment()
    
    # 3. Determine orchestrator sequence
    should_run_manifest = not args.pdfs_only
    should_run_pdfs = not args.manifest_only
    
    if should_run_manifest:
        # Check if we already have a manifest and aren't forcing a refresh
        if MANIFEST_PATH.exists() and not args.force_new_manifest:
            print(f"ℹ️ Found existing manifest blueprint at {MANIFEST_PATH.relative_to(ROOT_DIR)}.")
            print("   Using existing blueprint. Run with --force-new-manifest to regenerate it.\n")
        else:
            print("🚀 Step 1: Generating JSON manifest blueprint...")
            run_script("generate_manifest.py")
            print("✅ Step 1 complete!\n")
            
    if should_run_pdfs:
        print("🚀 Step 2: Compiling professional corporate PDFs...")
        run_script("generate_pdfs.py")
        print("✅ Step 2 complete!\n")
        
    print("======================================================================")
    print("🎉 Done! All generated PDFs are stored in 'agents/strat_agent/data/docs/'.")
    print("======================================================================")

if __name__ == "__main__":
    main()
