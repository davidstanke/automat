#!/usr/bin/env python3
# /// script
# dependencies = [
#   "google-genai",
#   "pydantic",
#   "python-dotenv",
# ]
# ///
"""
GeniCo Document Corpus Generator - Step 1: Manifest Generator
This script uses Gemini 2.5 Flash to brainstorm and structure a comprehensive
corpus of corporate documents for the fictional company GeniCo.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

# Load environment variables from the root .env
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

# Define structured schemas for Pydantic
class Section(BaseModel):
    title: str = Field(description="The title of the section, e.g., '1. Executive Summary' or '3. Technical Specifications'")
    prompt_instructions: str = Field(description="Detailed instructions telling Gemini what to write in this section. Ask for specific technical details, fictional metrics, tables, and paragraphs to make it extremely detailed.")

class ChartConfig(BaseModel):
    type: str = Field(description="The chart type: 'bar', 'line', or 'pie'")
    title: str = Field(description="Title of the chart")
    data: Dict[str, float] = Field(description="A dictionary of keys and float values to plot, e.g., {'Q1': 120.5, 'Q2': 150.2}")
    xlabel: Optional[str] = Field(None, description="Label for the X-axis")
    ylabel: Optional[str] = Field(None, description="Label for the Y-axis")

class DocumentManifest(BaseModel):
    filename: str = Field(description="The target filename, e.g., 'smartfridge_prd.pdf' (use lowercase with underscores)")
    title: str = Field(description="The full formal title of the document")
    doc_type: str = Field(description="The type of document, e.g., 'PRD', 'Meeting Notes', 'Project Plan', 'Strategy Doc', 'Operations Manual'")
    department: str = Field(description="The departmental owner, e.g., 'Product Management', 'Engineering', 'Operations', 'Executive', 'Customer Service'")
    author: str = Field(description="The name and title of the fictional author, e.g., 'Dr. Aris Vance, Chief Architect'")
    date: str = Field(description="A fictional date for the document in YYYY-MM-DD format (set around mid-2026)")
    summary: str = Field(description="A concise summary of what this document covers")
    sections: List[Section] = Field(description="3 to 5 logical sections for the document's body")
    charts: Optional[List[ChartConfig]] = Field(default=None, description="Up to 2 optional charts to embed in the document")

class ManifestList(BaseModel):
    documents: List[DocumentManifest]

def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    if api_key:
        print("🔑 Authenticating via GEMINI_API_KEY...")
        return genai.Client(api_key=api_key)
    elif project_id:
        print(f"☁️ Authenticating via Gemini Enterprise Agent Platform (GEAP) ADC (Project: {project_id}, Region: {location})...")
        return genai.Client(vertexai=True, project=project_id, location=location)
    else:
        raise ValueError(
            "Neither GEMINI_API_KEY nor GOOGLE_CLOUD_PROJECT_ID is set. "
            "Please configure one of these in your environment or root .env file."
        )


def generate_manifest():
    print("Initializing Gemini Client...")
    try:
        client = get_gemini_client()
    except Exception as e:
        print(f"Error: {e}")
        return

    print("Generating corporate corpus manifest via gemini-2.5-flash...")
    
    prompt = """
    You are the Corporate Communications & Information Architect for GeniCo, a massive, highly successful global manufacturer of smart home appliances, consumer electronics, and home energy/climate products.
    
    We need to build a realistic and diverse corpus of exactly 15 internal documents to populate our enterprise knowledge base.
    These documents must be highly realistic, cohesive, and deeply detailed. They should cover different fictional products and cross-functional operations of GeniCo, including:
    - Smart Home Appliances: GeniCo SmartFridge Pro (AI inventory), GeniCo WhisperWash (steam laundry), GeniCo OmniChef (combination smart oven).
    - Consumer Electronics: GeniCo VisionSphere (VR headset), GeniCo AuraSound (smart speaker system), GeniCo GeniTab (high-end tablets).
    - Home Energy & Climate: GeniCo PowerGrid Home (battery backup), GeniCo AuraPurify (smart HEPA air purifier), GeniCo GeniTherm (smart thermostat).
    
    The documents should represent a rich variety of types:
    1. Product Requirement Documents (PRDs)
    2. Executive Strategy & Market Analysis Docs
    3. Technical Operations Manuals & Runbooks
    4. Project/Implementation Plans (with timelines)
    5. High-stakes Post-Mortems or Meeting Notes
    
    Brainstorm exactly 15 documents. Ensure:
    - Balanced distribution across the 3 product divisions (Smart Appliances, Consumer Electronics, Home Energy).
    - Diverse authorship (engineers, PMs, VPs, directors, legal, operations).
    - Diverse departments (Product Management, R&D, Executive, Operations, Marketing, Legal, QA).
    - Professional, corporate, realistic document titles.
    - Detailed sections (each doc should have 3 to 5 logical sections, with precise prompt instructions for writing those sections).
    - Inline charts: At least 8 of the 15 documents should contain a professional chart (bar, line, or pie) representing realistic metrics (e.g., thermal performance, user adoption rates, battery cycle degradation, QA test results).
    
    Return the response strictly adhering to the ManifestList schema.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': ManifestList,
                'temperature': 0.7,
            }
        )
        
        # Parse the JSON response
        manifest_data = json.loads(response.text)
        
        # Create output directories
        output_dir = Path(__file__).resolve().parent / "manifests"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        manifest_path = output_dir / "docs_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2)
            
        print(f"\nSuccess! Generated corpus manifest with {len(manifest_data['documents'])} documents.")
        print(f"Manifest saved to: {manifest_path.relative_to(ROOT_DIR)}")
        
        # Print summaries of the generated documents
        print("\nGenerated Document Plan:")
        for idx, doc in enumerate(manifest_data['documents'], 1):
            charts_info = f" ({len(doc['charts'])} chart(s))" if doc.get('charts') else ""
            print(f"{idx:02d}. [{doc['doc_type']}] {doc['title']} by {doc['author']}{charts_info}")
            
    except Exception as e:
        print(f"Failed to generate manifest: {e}")

if __name__ == "__main__":
    generate_manifest()
