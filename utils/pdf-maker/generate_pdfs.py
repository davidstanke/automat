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
GeniCo Document Corpus Generator - Step 2: PDF Compiler
This script reads the generated JSON manifest, generates charts via Matplotlib,
queries Gemini 2.5 Flash to write detailed corporate content, converts markdown
to ReportLab Flowables, and builds high-quality, professional PDFs.
"""

import os
import re
import sys
import tempfile
import json
import time
import random
import threading
import concurrent.futures
from pathlib import Path
from dotenv import load_dotenv


# Load environment variables from the root .env
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")

# Check and warn if imports are missing before proceeding
try:
    from google import genai
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.colors import HexColor
    from reportlab.pdfgen import canvas
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
except ImportError as e:
    print(f"Error: Missing dependency. {e}")
    print("Please install required dependencies via 'pip install -r requirements.txt'")
    sys.exit(1)

# Helper function to get Gemini Client
def get_gemini_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    if api_key:
        return genai.Client(api_key=api_key)
    elif project_id:
        return genai.Client(vertexai=True, project=project_id, location=location)
    else:
        raise ValueError("Neither GEMINI_API_KEY nor GOOGLE_CLOUD_PROJECT_ID is set. Please add one to your environment or root .env file.")


# ----------------------------------------------------------------------
# 1. Custom Two-Pass Canvas for Dynamic "Page X of Y" & Headers
# ----------------------------------------------------------------------
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        # Save page states for the second pass
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        # Skip running header/footer on the first page if it is a cover page
        if self._pageNumber == 1 and getattr(self, 'is_cover_page', True):
            return

        self.saveState()
        
        primary_color = HexColor('#1A365D')
        text_color = HexColor('#4A5568')
        line_color = HexColor('#E2E8F0')
        
        # 1. Header (Letter height is 792, width is 612. Margins are 54)
        self.setStrokeColor(line_color)
        self.setLineWidth(0.5)
        self.line(54, 745, 558, 745)
        
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(primary_color)
        self.drawString(54, 750, "GeniCo Confidential")
        
        self.setFont("Helvetica", 8)
        self.setFillColor(text_color)
        doc_type = getattr(self, 'doc_type', 'Document')
        dept = getattr(self, 'department', 'Internal')
        self.drawRightString(558, 750, f"{doc_type.upper()} | {dept.upper()}")
        
        # 2. Footer
        self.line(54, 45, 558, 45)
        
        self.setFont("Helvetica", 8)
        self.setFillColor(text_color)
        doc_title = getattr(self, 'doc_title', 'Internal Document')
        self.drawString(54, 32, doc_title)
        self.drawRightString(558, 32, f"Page {self._pageNumber} of {total_pages}")
        
        self.restoreState()

def make_numbered_canvas_class(doc_title, doc_type, department, is_cover_page=True):
    class CustomNumberedCanvas(NumberedCanvas):
        def __init__(self, *args, **kwargs):
            self.doc_title = doc_title
            self.doc_type = doc_type
            self.department = department
            self.is_cover_page = is_cover_page
            super().__init__(*args, **kwargs)
    return CustomNumberedCanvas


# ----------------------------------------------------------------------
# 2. Beautiful Matplotlib Chart Generator
# ----------------------------------------------------------------------
def generate_chart(chart_config, temp_dir):
    chart_type = chart_config.get('type', 'bar')
    title = chart_config.get('title', 'Corporate Performance')
    data = chart_config.get('data', {})
    xlabel = chart_config.get('xlabel', '')
    ylabel = chart_config.get('ylabel', '')
    
    fig, ax = plt.subplots(figsize=(5.5, 2.8), dpi=300)
    
    primary_color = '#1A365D'
    accent_color = '#0D9488'
    slate_color = '#4A5568'
    
    keys = list(data.keys())
    values = list(data.values())
    
    if chart_type == 'bar':
        bars = ax.bar(keys, values, color=primary_color, edgecolor=slate_color, width=0.45)
        # Value tags on top of bars
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.1f}' if isinstance(height, float) else f'{height}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=7.5, color=slate_color, fontweight='semibold')
    elif chart_type == 'line':
        ax.plot(keys, values, color=accent_color, marker='o', linewidth=2.5, markersize=5.5)
        # Value tags on points
        for x, y in zip(keys, values):
            ax.annotate(f'{y:.1f}' if isinstance(y, float) else f'{y}',
                        xy=(x, y),
                        xytext=(0, 5),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=7.5, color=slate_color, fontweight='semibold')
    elif chart_type == 'pie':
        colors = [primary_color, accent_color, '#3182CE', '#319795', '#4A5568', '#718096', '#A0AEC0']
        ax.pie(values, labels=keys, colors=colors[:len(keys)], autopct='%1.1f%%',
               startangle=140, textprops={'fontsize': 7.5, 'color': slate_color, 'fontweight': 'semibold'})
               
    if chart_type != 'pie':
        ax.set_title(title, fontsize=9.5, fontweight='bold', color=primary_color, pad=10)
        ax.set_xlabel(xlabel, fontsize=7.5, color=slate_color, labelpad=4)
        ax.set_ylabel(ylabel, fontsize=7.5, color=slate_color, labelpad=4)
        ax.tick_params(axis='both', which='major', labelsize=7.5, labelcolor=slate_color)
        
        # Style spines
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#E2E8F0')
        ax.spines['bottom'].set_color('#E2E8F0')
        
        ax.grid(axis='y', linestyle='--', alpha=0.4, color='#CBD5E0')
    else:
        ax.set_title(title, fontsize=9.5, fontweight='bold', color=primary_color, pad=10)
        
    plt.tight_layout()
    
    # Save chart cleanly
    chart_filename = f"chart_{abs(hash(title)) & 0xffffffff}.png"
    chart_path = Path(temp_dir) / chart_filename
    plt.savefig(chart_path, dpi=300, bbox_inches='tight', transparent=True)
    plt.close(fig)
    
    return str(chart_path)


# ----------------------------------------------------------------------
# 3. Robust Markdown Parser for ReportLab Flowables
# ----------------------------------------------------------------------
def build_table_flowable(table_data, styles):
    if not table_data or len(table_data) == 0:
        return Spacer(1, 1)
    
    formatted_data = []
    for row_idx, row in enumerate(table_data):
        formatted_row = []
        for cell in row:
            if row_idx == 0:
                formatted_row.append(Paragraph(cell, styles['GeniCoTableHeader']))
            else:
                formatted_row.append(Paragraph(cell, styles['GeniCoTableText']))
        formatted_data.append(formatted_row)
        
    # Printable area is 504 (612 page width - 108 margin)
    num_cols = len(table_data[0]) if table_data else 1
    col_width = 504.0 / num_cols
    col_widths = [col_width] * num_cols
    
    t = Table(formatted_data, colWidths=col_widths, hAlign='LEFT')
    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1A365D')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CBD5E0')),
    ]
    
    # Alternating rows
    for r in range(1, len(table_data)):
        if r % 2 == 0:
            ts.append(('BACKGROUND', (0, r), (-1, r), HexColor('#F7FAFC')))
            
    t.setStyle(TableStyle(ts))
    return t

def markdown_to_flowables(md_text, styles):
    flowables = []
    lines = md_text.split('\n')
    
    in_list = False
    in_table = False
    table_data = []
    
    def clean_xml_text(text):
        # Escape characters that break ReportLab's simple XML paragraph parser
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;').replace('>', '&gt;')
        
        # Convert Markdown formatting to basic HTML formatting supported by ReportLab Paragraph
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        text = re.sub(r'`(.*?)`', r'<font name="Courier">\1</font>', text)
        return text

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Handle empty line
        if not stripped:
            if in_table:
                flowables.append(build_table_flowable(table_data, styles))
                flowables.append(Spacer(1, 10))
                table_data = []
                in_table = False
            if in_list:
                in_list = False
            i += 1
            continue
            
        # Handle H1, H2, H3
        if stripped.startswith('# '):
            if in_table:
                flowables.append(build_table_flowable(table_data, styles))
                table_data = []
                in_table = False
            in_list = False
            flowables.append(Paragraph(clean_xml_text(stripped[2:]), styles['GeniCoH1']))
            
        elif stripped.startswith('## '):
            if in_table:
                flowables.append(build_table_flowable(table_data, styles))
                table_data = []
                in_table = False
            in_list = False
            flowables.append(Paragraph(clean_xml_text(stripped[3:]), styles['GeniCoH2']))
            
        elif stripped.startswith('### '):
            if in_table:
                flowables.append(build_table_flowable(table_data, styles))
                table_data = []
                in_table = False
            in_list = False
            flowables.append(Paragraph(clean_xml_text(stripped[4:]), styles['GeniCoH3']))
            
        # Handle Bullet Lists
        elif stripped.startswith('* ') or stripped.startswith('- ') or stripped.startswith('• '):
            if in_table:
                flowables.append(build_table_flowable(table_data, styles))
                table_data = []
                in_table = False
            in_list = True
            content = clean_xml_text(stripped[2:])
            flowables.append(Paragraph(f"&bull;&nbsp;&nbsp;{content}", styles['GeniCoBullet']))
            
        # Handle Tables
        elif stripped.startswith('|'):
            in_list = False
            in_table = True
            # Parse row cells
            cells = [clean_xml_text(cell.strip()) for cell in stripped.split('|')[1:-1]]
            # Ignore markdown separator line like |---|---|
            if all(re.match(r'^:?-+:?$', cell) for cell in cells):
                i += 1
                continue
            table_data.append(cells)
            
        # Handle Normal Paragraph
        else:
            if in_table:
                flowables.append(build_table_flowable(table_data, styles))
                table_data = []
                in_table = False
            if in_list:
                in_list = False
                
            flowables.append(Paragraph(clean_xml_text(stripped), styles['GeniCoBody']))
            
        i += 1
        
    # Flush remaining table
    if in_table and table_data:
        flowables.append(build_table_flowable(table_data, styles))
        
    return flowables


# ----------------------------------------------------------------------
# 4. Premium Cover Page Builder
# ----------------------------------------------------------------------
def add_cover_page(story, doc, styles):
    story.append(Spacer(1, 40))
    
    # Brand Identity Header
    story.append(Paragraph("<font size=28 color='#1A365D'><b>GeniCo</b></font>", styles['Normal']))
    story.append(Paragraph("<font size=9 color='#4A5568'>INTELLIGENT HOME &amp; ENTERPRISE SOLUTIONS</font>", styles['Normal']))
    
    story.append(Spacer(1, 100))
    
    # Document Type Pill
    doc_type_style = ParagraphStyle(
        name='DocTypePill',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=HexColor('#FFFFFF'),
        backColor=HexColor('#0D9488'),
        borderPadding=6,
        spaceAfter=15
    )
    story.append(Paragraph(f"&nbsp;&nbsp;{doc['doc_type'].upper()}&nbsp;&nbsp;", doc_type_style))
    
    story.append(Spacer(1, 10))
    
    # Document Title
    title_style = ParagraphStyle(
        name='CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=30,
        textColor=HexColor('#1A365D'),
        spaceAfter=15
    )
    story.append(Paragraph(doc['title'], title_style))
    
    # Corporate Accent bar
    divider = Table([['']], colWidths=[504], rowHeights=[4])
    divider.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#1A365D')),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(divider)
    
    story.append(Spacer(1, 20))
    
    # Document Executive Abstract
    summary_style = ParagraphStyle(
        name='CoverSummary',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=11,
        leading=16,
        textColor=HexColor('#4A5568'),
        spaceAfter=30
    )
    story.append(Paragraph(doc['summary'], summary_style))
    
    story.append(Spacer(1, 110))
    
    # Metadata Block
    meta_text = f"""
    <b>Prepared By:</b> {doc['author']}<br/>
    <b>Department:</b> {doc['department']}<br/>
    <b>Date:</b> {doc['date']}<br/>
    <b>Classification:</b> GeniCo Confidential - Internal Use Only
    """
    meta_style = ParagraphStyle(
        name='CoverMeta',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=16,
        textColor=HexColor('#4A5568')
    )
    story.append(Paragraph(meta_text, meta_style))
    
    story.append(PageBreak())


# Thread-safe logging lock and progress counters
progress_lock = threading.Lock()
completed_sections_count = 0
total_sections_count = 0

def call_with_retry(func, *args, max_retries=3, initial_delay=1.0, **kwargs):
    delay = initial_delay
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries:
                raise e
            sleep_time = delay * (1.5 + random.random() * 0.5)
            with progress_lock:
                print(f"      [Warning] API call failed. Retrying in {sleep_time:.2f}s... Error: {e}")
            time.sleep(sleep_time)
            delay *= 2.0

# ----------------------------------------------------------------------
# 5. Gemini 2.5 Flash Copywriter Engine
# ----------------------------------------------------------------------
def generate_section_content(client, doc, section, section_idx):
    global completed_sections_count
    
    prompt = f"""
    You are writing a section of a high-quality, professional corporate document for **GeniCo**, a global manufacturer of appliances and electronics.
    
    ### DOCUMENT CONTEXT
    - **Document Title**: {doc['title']}
    - **Document Type**: {doc['doc_type']}
    - **Author**: {doc['author']}
    - **Department**: {doc['department']}
    - **Date**: {doc['date']}
    - **Document Summary**: {doc['summary']}
    
    ### SECTION TO WRITE
    - **Section Title**: {section['title']}
    - **Specific Instructions**: {section['prompt_instructions']}
    
    ### FORMATTING & TONE GUIDELINES
    1. Write in a highly detailed, formal, corporate prose style. Ensure the text reads as if written by a seasoned executive, analyst, or senior engineer.
    2. Do NOT use any placeholder text, TBD, or brackets like "[Insert date]". Invent authentic metrics, fictional specifications, names, dates, and background context to make it feel entirely real.
    3. Use standard Markdown formatting:
       - Use bold (`**text**`) and italics (`*text*`) for emphasis.
       - Use bullet lists (`- item` or `* item`) or numbered lists to break down info.
       - Create realistic tables using Markdown grid tables (`| Col 1 | Col 2 |` followed by `|---|---|` and data rows) to present performance metrics, technical specs, or target timelines.
    4. Write extensively. Aim for 2-4 comprehensive, well-developed paragraphs. Do not wrap the response in a ```markdown block, just return raw markdown content.
    """
    
    def _api_call():
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={'temperature': 0.5}
        )
        return response.text.strip()
        
    try:
        content = call_with_retry(_api_call)
    except Exception as e:
        with progress_lock:
            print(f"    [Error] Gemini generation failed after retries for section '{section['title']}': {e}")
        content = f"**System Warning:** Section content could not be dynamically generated due to persistent rate limits or network issues. Original specifications: {section['prompt_instructions']}"
        
    with progress_lock:
        completed_sections_count += 1
        print(f"✨ [Progress] Copy generated for {completed_sections_count}/{total_sections_count} sections... ({section['title'][:30]}...)")
        
    return content



# ----------------------------------------------------------------------
# 6. Corporate Style Definitions
# ----------------------------------------------------------------------
def create_custom_styles():
    styles = getSampleStyleSheet()
    
    primary_color = HexColor('#1A365D')
    charcoal_color = HexColor('#2D3748')
    
    styles.add(ParagraphStyle(
        name='GeniCoH1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=primary_color,
        spaceBefore=18,
        spaceAfter=10,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        name='GeniCoH2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=primary_color,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        name='GeniCoH3',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=13,
        textColor=charcoal_color,
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True
    ))

    styles.add(ParagraphStyle(
        name='GeniCoBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=charcoal_color,
        spaceBefore=0,
        spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        name='GeniCoBullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=charcoal_color,
        leftIndent=15,
        firstLineIndent=-10,
        spaceBefore=0,
        spaceAfter=4
    ))

    styles.add(ParagraphStyle(
        name='GeniCoTableText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=charcoal_color
    ))

    styles.add(ParagraphStyle(
        name='GeniCoTableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=HexColor('#FFFFFF')
    ))
    
    return styles


# ----------------------------------------------------------------------
# 7. Main Compilation Pipeline
# ----------------------------------------------------------------------
def compile_corpus():
    manifest_path = Path(__file__).resolve().parent / "manifests" / "docs_manifest.json"
    if not manifest_path.exists():
        print(f"Error: Manifest file not found at '{manifest_path}'. Please run step 1 first.")
        sys.exit(1)
        
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)
        
    documents = manifest_data.get("documents", [])
    if not documents:
        print("Error: No documents found in manifest.")
        sys.exit(1)
        
    try:
        client = get_gemini_client()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
        
    # Create final docs folder inside agents/strat_agent/data/docs
    output_docs_dir = ROOT_DIR / "agents" / "strat_agent" / "data" / "docs"
    output_docs_dir.mkdir(parents=True, exist_ok=True)
    
    styles = create_custom_styles()
    
    # Let's count sections and prepare concurrent copy generation tasks
    global total_sections_count, completed_sections_count
    completed_sections_count = 0
    
    tasks = []
    for doc in documents:
        for s_idx, section in enumerate(doc["sections"], 1):
            tasks.append((doc, section, s_idx))
            
    total_sections_count = len(tasks)
    
    print(f"\n🚀 Stage 1/2: Generating detailed copy for {total_sections_count} sections in parallel (ThreadPoolExecutor)...")
    
    # Map (doc_filename, section_title) to the generated Markdown content
    generated_copy_cache = {}
    
    # Run in parallel. 12 workers provides great throughput while respecting standard rate limits.
    max_workers = 12
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(generate_section_content, client, doc, section, s_idx): (doc["filename"], section["title"])
            for doc, section, s_idx in tasks
        }
        
        for future in concurrent.futures.as_completed(future_to_task):
            doc_filename, sec_title = future_to_task[future]
            try:
                content = future.result()
                generated_copy_cache[(doc_filename, sec_title)] = content
            except Exception as e:
                print(f"❌ Worker thread encountered exception: {e}")
                generated_copy_cache[(doc_filename, sec_title)] = f"**Error:** Unhandled error during generation. {e}"

    copy_duration = time.time() - start_time
    print(f"\n⚡ Copy generation complete! Generated {total_sections_count} sections in {copy_duration:.2f} seconds.")
    
    print(f"\n🚀 Stage 2/2: Assembling and compiling PDF files on disk...")
    assembly_start = time.time()
    
    # Create a temporary folder for matplotlib chart rendering
    with tempfile.TemporaryDirectory() as temp_dir:
        for idx, doc in enumerate(documents, 1):
            doc_start = time.time()
            
            # 1. Render charts if defined
            charts_flowables = []
            if doc.get('charts'):
                for c_idx, chart_cfg in enumerate(doc['charts'], 1):
                    try:
                        chart_path = generate_chart(chart_cfg, temp_dir)
                        # Center and scale chart image in flowable (5.5in width, 2.8in height -> 396x201 points)
                        charts_flowables.append(Image(chart_path, width=396, height=201))
                    except Exception as e:
                        print(f"    [Error] Chart generation failed: {e}")
            
            # 2. Build story list
            story = []
            
            # Only use Cover page for long document types (PRDs, Strategy, Manuals, Projects)
            use_cover = doc['doc_type'].lower() in ['prd', 'strategy doc', 'operations manual', 'project plan']
            
            if use_cover:
                add_cover_page(story, doc, styles)
            else:
                # Add simplified title banner for shorter docs like Meeting Notes
                story.append(Paragraph(f"<font size=10 color='#0D9488'><b>GENICO {doc['doc_type'].upper()}</b></font>", styles['Normal']))
                story.append(Paragraph(doc['title'], styles['GeniCoH1']))
                story.append(Paragraph(f"<b>Prepared By:</b> {doc['author']} | <b>Date:</b> {doc['date']} | <b>Classification:</b> Confidential", styles['GeniCoBody']))
                story.append(Spacer(1, 10))
                story.append(Table([['']], colWidths=[504], rowHeights=[1], style=[('BACKGROUND', (0,0), (-1,-1), HexColor('#1A365D'))]))
                story.append(Spacer(1, 15))
                story.append(Paragraph(doc['summary'], styles['GeniCoBody']))
                story.append(Spacer(1, 10))
                
            # 3. Retrieve text from cache and parse
            for section_idx, section in enumerate(doc['sections'], 1):
                section_text = generated_copy_cache.get((doc['filename'], section['title']), "")
                section_flowables = markdown_to_flowables(section_text, styles)
                story.extend(section_flowables)
                
                # Strategically inject charts inline
                if len(charts_flowables) > 0:
                    if section_idx == 1 and len(charts_flowables) >= 1:
                        story.append(Spacer(1, 10))
                        story.append(charts_flowables[0])
                        story.append(Spacer(1, 15))
                    elif section_idx == 3 and len(charts_flowables) >= 2:
                        story.append(Spacer(1, 10))
                        story.append(charts_flowables[1])
                        story.append(Spacer(1, 15))
                
                # Normal section break
                story.append(Spacer(1, 15))
                
            # 4. Compile the PDF document
            pdf_path = output_docs_dir / doc['filename']
            doc_template = SimpleDocTemplate(
                str(pdf_path),
                pagesize=letter,
                leftMargin=54,
                rightMargin=54,
                topMargin=54,
                bottomMargin=54
            )
            
            canvas_class = make_numbered_canvas_class(
                doc_title=doc['title'],
                doc_type=doc['doc_type'],
                department=doc['department'],
                is_cover_page=use_cover
            )
            
            doc_template.build(story, canvasmaker=canvas_class)
            doc_duration = time.time() - doc_start
            print(f"📄 [Success] Compiled {idx:02d}/{len(documents)}: agents/strat_agent/data/docs/{doc['filename']} in {doc_duration:.2f}s")

    total_duration = time.time() - start_time
    print(f"\n🎉 PDF Corpus Compilation Complete! All documents compiled in {total_duration:.2f} seconds.")

if __name__ == "__main__":
    compile_corpus()

