# ---------------------------
# IMPORTS
# ---------------------------

# Standard library
import asyncio
import gzip
import io
from io import StringIO
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
import json
import errno
import shlex
import traceback
import tempfile

# Third-party
import plotly.express as px
from shinywidgets import output_widget, render_widget
from plotly.graph_objs import Figure
import paramiko
import posixpath
import stat
import zipfile
from paramiko.sftp_client import SFTPClient
import pandas as pd
import aiohttp
from asyncio import Event
from tqdm import tqdm
import math
from scp import SCPClient
from shiny import App, Inputs, Outputs, Session, reactive, render, ui
from shiny.types import FileInfo

# Local application
from auth.auth_db import init_db
from auth.auth import AuthManager

# ---------------------------
# CONFIGURATION & CONSTANTS
# ---------------------------

# Initialize database and authentication system
init_db()
auth = AuthManager()

# Path configurations
DATA_DIR = Path(__file__).parent / "data"

# API request configurations
TIMEOUT = aiohttp.ClientTimeout(total=60)  # 60 second timeout for UniProt requests
BATCH_SIZE = 50  # Number of concurrent downloads
RETRIES = 3  # Number of retries for failed downloads

# UniProt URLs for proteome data
REF_URL = "https://rest.uniprot.org/proteomes/stream?compressed=true&fields=upid%2Corganism%2Cprotein_count%2Clineage&format=tsv&query=%28*%29+AND+%28proteome_type%3A1%29"
OTHER_URL = "https://rest.uniprot.org/proteomes/stream?compressed=true&fields=upid%2Corganism%2Cprotein_count%2Clineage&format=tsv&query=%28*%29+AND+%28proteome_type%3A2%29&sort=cpd+asc"


# ---------------------------
# DATA MANAGEMENT
# ---------------------------

# Reactive container for proteome data
data = reactive.Value({
    "ref": pd.DataFrame(),
    "other": pd.DataFrame()
})

async def fetch_data(session, url, retries=2):
    """Fetch and decompress data from a URL asynchronously."""
    for attempt in range(retries):
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                compressed_data = await response.read()
                return gzip.decompress(compressed_data).decode('utf-8')
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

async def fetch_uniprot_proteomes_async():
    """Fetch reference and other proteomes from UniProt asynchronously."""
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            ref_data, other_data = await asyncio.gather(
                fetch_data(session, REF_URL),
                fetch_data(session, OTHER_URL))
            
            ref_df = pd.read_csv(StringIO(ref_data), sep='\t').dropna(subset=['Organism'])
            other_df = pd.read_csv(StringIO(other_data), sep='\t').dropna(subset=['Organism'])
            
            return ref_df, other_df
            
    except Exception as e:
        print(f"Error fetching remote data: {e}")
        # Fallback to local data if available
        try:
            ref_df = pd.read_csv(DATA_DIR / "ref.tsv", sep="\t")
            other_df = pd.read_csv(DATA_DIR / "other.tsv", sep="\t")
            print("Using local data fallback")
            return ref_df, other_df
        except Exception as local_error:
            print(f"Local data load failed: {local_error}")
            return pd.DataFrame(), pd.DataFrame()

# Initialize loading state
_data_loaded_event = Event()
_data = {"ref": pd.DataFrame(), "other": pd.DataFrame()}

async def load_proteome_data():
    """Load data wrapper with error handling"""
    try:
        ref_df, other_df = await fetch_uniprot_proteomes_async()
        data.set({"ref": ref_df, "other": other_df})
        print("Proteome data loaded successfully")
    except Exception as e:
        print(f"Critical data load failure: {e}")
        data.set({"ref": pd.DataFrame(), "other": pd.DataFrame()})

# ---------------------------
# UI COMPONENTS
# ---------------------------

def landing_page() -> ui.Tag:
    """Create the landing page UI."""
    return ui.div(
        ui.div(
            ui.div(
                ui.h1("Meet COGnition", class_="display-3 fw-light text-center mb-3"),
                ui.p(
                    "Precision metaproteomics through COG-based database curation",
                    class_="lead text-center text-muted mb-4"
                ),
                ui.div(
                    ui.a(
                        "Begin Analysis →",
                        href="#",
                        onclick="Shiny.setInputValue('navbar', 'Proteome Browser', {priority: 'event'}); return false;",
                        class_="btn btn-success btn-lg"
                    ),
                    class_="text-center"
                ),
                class_="col-lg-8 mx-auto py-5"
            ),
            class_="container border-bottom py-5"
        ),
        ui.div(
            ui.div(
                ui.div(
                    ui.h2("Why COGnition?", class_="h5 text-uppercase text-muted mb-4"),
                    ui.tags.ul(
                        ui.tags.li(ui.strong("Focused Databases:"), " Reduce search space using evolutionary conserved COGs."),
                        ui.tags.li(ui.strong("Lower FDR:"), " Achieve more confident identifications by eliminating irrelevant taxa."),
                        ui.tags.li(ui.strong("Scalable Workflow:"), " Process diverse microbiome samples without manual pre-filtering."),
                        class_="list-unstyled"
                    ),
                    class_="col-md-6"
                ),
                ui.div(
                    ui.h2("How It Works", class_="h5 text-uppercase text-muted mb-4"),
                    ui.tags.ol(
                        ui.tags.li(ui.strong("COG Screening:"), " Initial search against a non-redundant COG database."),
                        ui.tags.li(ui.strong("Proteome Retrieval:"), " Automatic fetching of complete proteomes from UniProt."),
                        ui.tags.li(ui.strong("Precise Identification:"), " Final spectral matching against your customized database."),
                        class_="list-unstyled"
                    ),
                    class_="col-md-6"
                ),
                class_="row gx-5"
            ),
            class_="container py-5 border-bottom"
        ),
        ui.div(
            ui.div(
                ui.h2("Ready to optimize your metaproteomics?", class_="h4 fw-light text-center mb-4"),
                ui.div(
                    ui.a(
                        "Launch Proteome Browser",
                        href="#",
                        onclick="Shiny.setInputValue('navbar', 'Proteome Browser', {priority: 'event'}); return false;",
                        class_="btn btn-success btn-lg"
                    ),
                    class_="text-center"
                ),
                class_="col-lg-6 mx-auto py-4"
            ),
            class_="container bg-light py-5"
        )
    )

def browser_page() -> ui.Tag:
    """Create the proteome browser page UI."""
    return ui.page_sidebar(
        ui.sidebar(
            ui.h2("Filter Controls", class_="text-success mb-3"),
            ui.div(
                ui.input_text_area(
                    "taxa_list", 
                    "Enter Taxa (comma-separated):",
                    placeholder="e.g., Escherichia, Streptococcus",
                    rows=3
                ),
            ui.input_file(
                "taxa_file", 
                "Upload taxa file:",
                accept=[".csv", ".tsv", ".txt"],
                multiple=False
            ),
                class_="mb-2" 
            ), 
            ui.div(
                ui.input_checkbox_group(
                    "proteome_types",
                    "",
                    {
                        "ref": ui.span("Reference Proteomes", ui.output_text("ref_count_badge", inline=True)),
                        "other": ui.span("Other Proteomes", ui.output_text("other_count_badge", inline=True)),
                    },
                    selected=["ref", "other"],
                    inline=False
                ),
                class_="mb-2"
            ),
            ui.div(
                ui.input_select(
                    "page_size",
                    "Results per page:",
                    {"10": "10", "25": "25", "50": "50", "100": "100"},
                    selected="10"
                ),
                class_="mb-4"
            ),
            ui.div(
                ui.input_checkbox(
                    "remove_redundancy", 
                    "Remove redundant proteomes", 
                    False
                ),
                class_="mb-3"
            ),
            ui.div(
                ui.input_action_button(
                    "apply_filters", 
                    "Apply Filters",
                    class_="btn-success w-100"
                ),
                class_="mb-3"
            ),
            ui.hr(class_="my-4"),
            ui.div(
                ui.input_action_button(
                    "prepare_download",
                    ui.TagList(
                        ui.tags.i(class_="bi bi-download me-2"),
                        "Prepare FASTA Download"
                    ),
                    class_="btn-outline-success w-100"
                ),
                ui.output_ui("download_status_ui"),
                ui.output_ui("download_failed_ui")
            ),
            width=330,
            open="open",
            gap=5
        ),
        ui.layout_columns(
            ui.value_box(
                "Filtered Proteomes",
                ui.output_text("filtered_proteome_count"),
                showcase=ui.tags.i(class_="bi bi-funnel-fill text-success"),
                class_="border-success custom-value-box",
                height="160px"
            ),
            ui.value_box( 
                "Protein Coverage",
                ui.output_text("protein_coverage"),
                showcase=ui.tags.i(class_="bi bi-bar-chart-fill text-success"),
                class_="border-success custom-value-box",
                height="160px" 
            ),
            ui.div( 
                output_widget("proteome_pie", width="100%"),
                class_="chart-container",
                style="height: 160px; min-width: 0;" 
            ), 
            col_widths=(4, 4, 4),
            class_="m-0 g-0 p-0",
            height="auto"
        ),
        ui.tags.style("""
            @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
            .custom-value-box {
                padding: 8px !important;
                display: flex;
                flex-direction: column;
                justify-content: center;
                overflow: hidden;
            }
            .custom-value-box .value-box-title {
                font-size: 0.9rem !important;
                margin-bottom: 4px !important;
            }
            .custom-value-box .value-box-value {
                font-size: 1.8rem !important;
                line-height: 1.2 !important;
            }
            .custom-value-box .bi {
                font-size: 3.0rem !important;
                margin-left: 8px !important;
            }
            .chart-container {
                width: 100%;
                height: 100%;
                padding: 8px !important;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            /* Add this critical flex containment */
            .chart-container > * {
                flex: 1 1 auto;
                min-width: 0;
                min-height: 0;
            }
            .row > [class^="col-"] {
                min-height: 0;
                min-width: 0;
            }
        """),
        ui.layout_columns(
            ui.card(
                ui.card_header(
                    ui.h3("Proteome Browser", class_="text-success mb-0", style="font-size: 1.1rem;"),
                    ui.tooltip(
                        ui.tags.i(class_="bi bi-info-circle text-success"),
                        "Browse and filter proteome data from UniProt",
                        placement="right"
                    ),
                    class_="d-flex justify-content-between align-items-center py-2"
                ),
                ui.output_data_frame("proteome_table"),
                ui.card_footer(
                    ui.layout_columns(
                        ui.input_action_button(
                            "prev_page", 
                            "← Previous",
                            class_="btn-outline-success btn-sm" 
                        ),
                        ui.div(
                            ui.output_text("page_status"),
                            class_="text-center small d-flex justify-content-center align-items-center"
                        ),
                        ui.input_action_button(
                            "next_page", 
                            "Next →",
                            class_="btn-outline-success btn-sm" 
                        ),
                        col_widths=(2, 8, 2),
                        gap=1
                    ),
                    class_="py-1"
                ),
                class_="border-success h-100",
                height="calc(100vh - 280px)",  
                full_screen=True
            ),
            col_widths=12,
            class_="g-0"
        ),
        fillable=True,
        gap=10
    )

def databases_page() -> ui.Tag:
    """Create the databases information page UI."""
    return ui.div(
        ui.div(
            ui.div(
                ui.div(
                    ui.div(
                        ui.h3("What are COGs?", class_="h4 text-success"),
                        ui.p(
                            "Clusters of Orthologous Groups (COGs) are phylogenetic classifications of proteins "
                            "from complete genomes that represent major phylogenetic lineages.",
                            class_="mb-2"
                        ),
                        ui.p(
                            "Each COG contains proteins that are orthologs - genes in different species that "
                            "evolved from a common ancestral gene, enabling precise evolutionary analysis.",
                            class_="mb-3"
                        ),
                        class_="card p-3 h-100 border-0"
                    ),
                    class_="col-md-6 mb-3"
                ),
                ui.div(
                    ui.div(
                        ui.h3("Why COGs for Metaproteomics?", class_="h4 text-success"),
                        ui.tags.ul(
                            ui.tags.li("Reduces database search space substantially"),
                            ui.tags.li("Maintains evolutionary and functional context"),
                            ui.tags.li("Enables more confident protein identification"),
                            ui.tags.li("Provides standardized functional classification"),
                            class_="mb-0"
                        ),
                        class_="card p-3 h-100 border-0"
                    ),
                    class_="col-md-6 mb-3"
                ),
                class_="row g-3"
            ),
            class_="mb-5 px-3"
        ),
        ui.div(
            ui.div(
                ui.div(
                    ui.h4("Uniprot Reference Collection", class_="text-success"),
                    ui.h5("Foundational Database", class_="h6 text-muted"),
                    ui.hr(),
                    ui.p(
                        "Comprehensive collection of COG classifications serving as the foundation for all "
                        "specialized subsets. Regularly updated with new genomes and annotations.",
                        class_="mb-3"
                    ),
                    ui.tags.ul(
                        ui.tags.li("Complete COG classifications from Uniprot"),
                        ui.tags.li("Non-redundant protein sequences"),
                        ui.tags.li("Organism taxonomic annotations"),
                        ui.tags.li("Regularly updated with new discoveries"),
                        class_="small mb-4"
                    ),
                    ui.div(
                        ui.input_action_button(
                            "download_core",
                            label=ui.TagList(
                                ui.tags.i(class_="bi bi-download me-2"),
                                "Download Core Database"
                            ),
                            class_="btn-success w-100",
                            disabled=True
                        ),
                        class_="d-grid gap-2"
                    ),
                    class_="card-body"
                ),
                class_="card h-100 border-success"
            ),
            class_="mb-5"
        ),
        ui.div(
            ui.h2("Site-Specific Databases", class_="text-success mt-4 mb-3"),
            ui.p(
                "Specialized subsets for microbiome research contexts:",
                class_="lead mb-4"
            ),
            ui.div(
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h4("Gut Microbiome", class_="text-success"),
                            ui.h5("UHGP Database", class_="h6 text-muted"),
                            ui.hr(),
                            ui.p(
                                "204,938 non-redundant genomes from gastrointestinal microbiomes. "
                                "Enables precise analysis of gut microbial functions and interactions."
                            ),
                            ui.tags.ul(
                                ui.tags.li("Comprehensive gut microbial coverage"),
                                ui.tags.li("Optimized for metaproteomic analysis"),
                                ui.tags.li("Includes functional annotations"),
                                class_="small"
                            ),
                            ui.input_action_button(
                                "download_uhgp",
                                label=ui.TagList(
                                    ui.tags.i(class_="bi bi-download me-2"),
                                    "Download UHGP Subset"
                                ),
                                class_="btn-outline-success w-100 mt-3",
                                disabled=True
                            ),
                            class_="card-body"
                        ),
                        class_="card h-100 border-success"
                    ),
                    class_="col-md-6 mb-4"
                ),
                ui.div(
                    ui.div(
                        ui.div(
                            ui.h4("Vaginal Microbiome", class_="text-success"),
                            ui.h5("VIRGO Database", class_="h6 text-muted"),
                            ui.hr(),
                            ui.p(
                                "0.95 million non-redundant genes from vaginal microbiomes. "
                                "Essential for studying female reproductive health and associated microbes."
                            ),
                            ui.tags.ul(
                                ui.tags.li("Comprehensive vaginal microbial genes"),
                                ui.tags.li("Clinical research optimized"),
                                ui.tags.li("Includes health-state annotations"),
                                class_="small"
                            ),
                            ui.input_action_button(
                                "download_virgo",
                                label=ui.TagList(
                                    ui.tags.i(class_="bi bi-download me-2"),
                                    "Download VIRGO Subset"
                                ),
                                class_="btn-outline-success w-100 mt-3",
                                disabled=True
                            ),
                            class_="card-body"
                        ),
                        class_="card h-100 border-success"
                    ),
                    class_="col-md-6 mb-4"
                ),
                class_="row"
            ),
            ui.div(
                ui.p(
                    "Additional specialized databases coming soon: oral, skin, and environmental microbiomes.",
                    class_="text-muted text-center mt-3"
                ),
                class_="col-12"
            ),
            class_="mt-4"
        ),
        class_="container py-4"
    )

def hpc_page() -> ui.Tag:
    """Create HPC interface page with terminal-like styling."""
    return ui.page_sidebar(
        ui.sidebar(
            ui.h2("HPC Connection", class_="text-success mb-3"),
            ui.input_text("hpc_host", "Hostname", placeholder="hpc.example.com"),
            ui.input_text("hpc_user", "Username"),
            ui.input_password("hpc_pass", "Password"),
            ui.layout_columns(
                ui.input_action_button("hpc_connect", "Connect", class_="btn-success"),
                ui.input_action_button("hpc_disconnect", "Disconnect", class_="btn btn-secondary"),
                col_widths=(6, 6)
            ),
            ui.hr(class_="my-4"),
            ui.input_file("hpc_upload", "Upload Files", multiple=True),
            ui.input_action_button("hpc_transfer", "Start Transfer", class_="btn-outline-success"),
            ui.hr(class_="my-4"),
            ui.input_action_button("create_job", "Create SLURM Job", class_="btn-success"),
            ui.hr(class_="my-4"),
            width=350,
            gap=6,

        ),
        ui.layout_columns(
            # Left Column - Terminal
            ui.card(
                ui.card_header(
                    "HPC Terminal",
                    ui.tooltip(
                        ui.tags.i(class_="bi bi-info-circle text-success"),
                        "Execute commands on the connected HPC",
                        placement="right"
                    )
                ),
                ui.div(
                    ui.output_ui("hpc_pwd"),
                    ui.div(
                        ui.div(
                            "Enter Shell Command:",
                            class_="form-label"
                        ),
                        ui.input_text_area(
                            "hpc_command",
                            label=None,
                            placeholder="'Ctrl + Enter' to execute",
                            height="75px",
                            width="100%"
                        ),
                        class_="mb-3"
                    ),
                    ui.div(
                        ui.pre(
                            ui.code(
                                ui.output_text("hpc_output"),
                            ),
                            id="terminal-output",
                            class_="terminal-output bg-secondary text-light p-3 rounded"
                        ),
                        style="height: 70vh; min-height: 300px; overflow-y: auto;"
                    ),
                    class_="h-100",
                ),
                class_="border-success",
                full_screen=True,
                height="70vh"
            ),

            # Right Column - File Browser and Editor
            ui.div(
                ui.card(
                    ui.card_header("File Browser"),
                    ui.output_data_frame("hpc_file_browser"),
                    ui.card_footer(
                        ui.layout_columns(
                            ui.input_action_link(
                                "hpc_open",
                                ui.tags.i(class_="bi bi-folder2-open"),
                                class_="btn btn-sm text-success",
                                title="Open selected item"
                            ),
                            ui.input_action_link(
                                "hpc_delete", 
                                ui.tags.i(class_="bi bi-trash"),
                                class_="btn btn-sm text-danger",
                                title="Delete"
                            ),
                            ui.download_link(
                                "hpc_download_handler",
                                ui.tags.i(class_="bi bi-download"),
                                class_="btn btn-sm text-success",
                                title="Download"
                            ),
                            ui.input_action_link(
                                "hpc_refresh",
                                ui.tags.i(class_="bi bi-arrow-clockwise"),
                                class_="btn btn-sm text-success",
                                title="Refresh"
                            ),
                            col_widths=(3, 3, 3, 3),
                            gap=0
                        ),
                        class_="py-2"
                    ),
                    class_="border-success",
                    height="50vh",
                    full_screen=True
                ),
                ui.card(
                    ui.card_header(
                        "Job Queue",
                        ui.tooltip(
                            ui.tags.i(class_="bi bi-info-circle text-success"),
                            "Currently running/pending jobs for your account",
                            placement="right"
                        ),
                        ui.input_action_link(
                            "refresh_queue",
                            ui.tags.i(class_="bi bi-arrow-clockwise"),
                            class_="btn btn-sm text-success",
                            title="Refresh"
                        )
                    ), 
                    ui.output_data_frame("job_queue_table"),
                    class_="mt-3 border-success",
                    height="250px"
                ),
                class_="h-100 d-flex flex-column",
                style="min-height: 70vh; height: 70vh;"
            ),
            col_widths=(7, 5),
            height="auto",
            style="min-height: 70vh;"
            ),
        # Additional CSS styling
        ui.tags.style("""
            /* Improved height management */
            .card {
                display: flex;
                flex-direction: column;
            }
            .card > .card-body {
                flex: 1;
                min-height: 200px;
                overflow: hidden;
            }
            .terminal-output {
                height: 100% !important;
                max-height: 55vh;
            }
            .data-grid-container {
                height: 100% !important;
                max-height: 60vh;
            }
        """)
    )


# ---------------------------
# MAIN APPLICATION UI
# ---------------------------

app_ui = ui.page_navbar(
    # Navigation items
    ui.nav_panel(" Home", landing_page(), icon=ui.tags.i(class_="bi bi-house text-success")),
    ui.nav_panel(" Databases", databases_page(), icon=ui.tags.i(class_="bi bi-database text-success")),
    ui.nav_panel(" Proteome Browser", browser_page(), icon=ui.tags.i(class_="bi bi-search text-success")),
    ui.nav_panel(" HPC Interface", hpc_page(), icon=ui.tags.i(class_="bi bi-terminal text-success")),

    # Authentication dropdown
    ui.nav_menu(
        " Account",
        ui.nav_control(
            ui.output_ui("auth_links"),
        ),
        icon=ui.tags.i(class_="bi bi-person-circle text-success"),
        align="right"
    ),
   
    # Footer and styling
    title=ui.div("COGnition", class_="d-flex align-items-center"),
    footer=ui.div(
        ui.hr(),
        ui.div("COGnition v1.0 · © 2025", class_="text-center text-muted py-3"),
        ui.output_ui("auth_modal"),
        ui.tags.link(
            rel="stylesheet",
            href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css"),
        ui.tags.style("""
            .user-greeting {
                font-weight: 500;
                padding-right: 1rem;
                color: var(--bs-success);
            }
            .data-grid-table tr.directory {
                background-color: var(--bs-light-bg-subtle);
                cursor: pointer;
            }
            .data-grid-table tr.directory:hover {
                background-color: var(--bs-light-bg-subtle);
                filter: brightness(0.98);
            }
            .data-grid-table td[data-colindex="0"] {
                padding-left: 1.8rem;
                position: relative;
            }
            .data-grid-table tr.directory td[data-colindex="0"]::before {
                content: '📁';
                position: absolute;
                left: 0.5rem;
                top: 50%;
                transform: translateY(-50%);
            }    
            .progress-bar {
                transition: width 0.3s ease;
                background-color: var(--bs-success);
            }
            .shiny-notification {
                border-left: 4px solid var(--bs-success);
            }        
            .data-grid-table td[data-colname='Taxonomic Lineage'] {
                position: relative;
            }
            .data-grid-table td[data-colname='Taxonomic Lineage']:hover::after {
                content: attr(title);
                position: absolute;
                left: 0;
                top: 100%;
                background: white;
                border: 1px solid #ccc;
                padding: 8px;
                z-index: 1000;
                min-width: 300px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.2);
                white-space: normal;
            }
             .btn-file-action {
                padding: 0.25rem 0.5rem;
                font-size: 0.875rem;
            }
            .file-editor-container {
                border: 1px solid #dee2e6;
                border-radius: 0.25rem;
                padding: 0.5rem;
                margin-top: 1rem;
            }
            .terminal-output {
                font-family: monospace;
                white-space: pre-wrap;
                background-color: #1e1e1e;
                color: #d4d4d4;
                border-radius: 0.3rem;
                padding: 1rem;
            }
             .btn-sm {
                padding: 0.25rem 0.5rem;
                font-size: 0.875rem;
                line-height: 1.5;
            }
            .btn-sm i {
                vertical-align: middle;
            }
            [title] {
                cursor: pointer;
            }
            .card-fullscreen {
                z-index: 1050 !important; /* Ensure editor appears above other elements */
                background-color: white;
            }
            #file_editor_card .card-body {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            #file_editor_card textarea {
                flex-grow: 1;
                resize: none;
            }
            .custom-editor-container textarea {
                border: none !important;
                background-color: transparent !important;
                padding: 0.75rem !important;
                resize: none;
                font-family: monospace;
                }
                /* More compact table rows */
                .data-grid-table tr {
                    line-height: 1.2;
            }
                    
            /* Smaller table font */
            .data-grid-table td, .data-grid-table th {
                font-size: 0.9em;
                padding: 4px 8px;
            }
            
            /* Tighten card margins */
            .card-body {
                padding: 0.5rem;
            }
            
             /* HPC Terminal Button Styling */
            #hpc_execute {
                padding: 0.25rem 0.5rem;
                font-size: 0.875rem;
                height: 38px;
                width: 38px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            #hpc_execute i {
                vertical-align: middle;
            }
            /* Make the command input fill available space */
            #hpc_command .shiny-input-container {
                width: 100%;
                margin-bottom: 0;
            }
            /* Label styling */
            .form-label {
                margin-bottom: 0.5rem;
                font-weight: 500;
            }
            /* Add brief flash animation when command submits */
            @keyframes commandSubmit {
                0% { background-color: inherit; }
                50% { background-color: #e8f5e9; }
                100% { background-color: inherit; }
            }
            .command-submitted {
                animation: commandSubmit 0.5s;
            }
            .selectize-dropdown {
                z-index: 9999 !important;  /* Ensure dropdown appears above modal */
            }
            .selectize-input {
                min-height: 38px;
            }
            .modal-header {
            border-bottom: 2px solid var(--bs-primary);
            padding-bottom: 0.5rem;
            }
            #job_commands {
                font-family: monospace;
                font-size: 0.9em;
                padding: 12px;
            }
            .modal-dialog {
                max-width: unset !important;
                margin: 0.5rem;
            }
            
            .code-editor textarea {
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.85em;
                background-color: #f8f9fa;
                border: 1px solid #dee2e6 !important;
                min-height: 300px;
            }
            
            .compact-input .form-label {
                font-size: 0.9em;
                margin-bottom: 0.25rem;
            }
            
            .compact-input .form-control {
                padding: 0.2rem 0.4rem;
                height: calc(1.4em + 0.4rem + 2px);
            }
            .three-col-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 1rem;
            }
            
            .compact-card .form-control {
                padding: 0.2rem 0.4rem;
                font-size: 0.875rem;
            }
            
            .compact-card .form-label {
                margin-bottom: 0.3rem;
                font-size: 0.9rem;
            }
            
            .code-editor textarea {
                min-height: 250px;
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.85em;
            }
            
            .modal-card-header {
                padding: 0.5rem 1rem;
                font-size: 0.95rem;
            }
            .bi-plus-lg {
                font-size: 1.2rem;
                vertical-align: middle;
            }
            .btn-module-add {
                line-height: 1;
                padding: 0.25rem 0.5rem;
            }
            /* Improved partition selector dropdown */
            .selectize-dropdown {
                max-height: 400px !important;
                overflow-y: auto !important;
                z-index: 99999 !important;
            }
            
            .selectize-dropdown-content {
                padding: 5px 0;
            }
            
            .selectize-dropdown [data-selectable] {
                padding: 8px 12px;
                line-height: 1.4;
            }
            
            .selectize-input.items.full.has-options.has-items {
                min-height: 38px;
                padding: 6px 12px;
            }
            
            /* Add smooth scrolling to dropdown */
            .selectize-dropdown-content {
                scroll-behavior: smooth;
            }     
            .data-grid-table {
                font-size: 0.8em;
                overflow-y: auto;
            }
                                    
        """),
        ui.tags.script("""
            $(document).on("shiny:value", function(e) {
                if(e.name === 'download_ready') {
                    if(e.value) {
                        $('#download_fasta').show();
                    } else {
                        $('#download_fasta').hide();
                    }
                }
            });

            $(document).ready(function() {
            $('#hpc_command').on('keydown', function(e) {
                if (e.ctrlKey && e.key === 'Enter') {
                    $(this).addClass('command-submitted');
                    setTimeout(() => $(this).removeClass('command-submitted'), 500);
                    Shiny.setInputValue('hpc_execute', Math.random(), {priority: 'event'});
                    e.preventDefault();
                }
            });
            
            Shiny.addCustomMessageHandler('clear_hpc_command', function(message) {
                $('#hpc_command')
                    .val('')
                    .focus()
                    .addClass('command-submitted');
                setTimeout(() => $('#hpc_command').removeClass('command-submitted'), 500);
            });
        });
            // Function to scroll terminal to bottom
            function scrollTerminalToBottom() {
                const terminal = document.getElementById('terminal-output');
                terminal.scrollTop = terminal.scrollHeight;
            }

            // Scroll initially
            scrollTerminalToBottom();

            // Set up observer to scroll when content changes
            const observer = new MutationObserver(scrollTerminalToBottom);
            observer.observe(document.getElementById('terminal-output'), {
                childList: true,
                subtree: true,
                characterData: true
            });

            // Also scroll when Shiny updates the output
            $(document).on('shiny:value', function(e) {
                if (e.name === 'hpc_output') {
                    scrollTerminalToBottom();
                }
            });
            
            """),
    ),
    navbar_options=ui.navbar_options(id="main_navbar")
)

# ---------------------------
# SERVER LOGIC
# ---------------------------

def server(input: Inputs, output: Outputs, session: Session):

    # ---------------------------
    # INITIALIZE DATA
    # ---------------------------

    @reactive.Effect
    async def init_data():
        # Will run once per session
        await load_proteome_data()

    # ---------------------------
    # AUTHENTICATION MANAGEMENT
    # ---------------------------
    auth_manager = AuthManager()
    auth_manager.server(input, output, session)

    @output
    @render.ui
    def auth_links():
        if auth_manager.current_user.get():
            return ui.TagList(
                ui.span(
                    f"Hello {auth_manager.current_user.get()['username']}!",
                    class_="nav-link user-greeting me-3"
                ),
                ui.a(
                    "Logout",
                    href="#",
                    onclick="Shiny.setInputValue('auth_logout', true, {priority: 'event'});",
                    class_="nav-link text-danger"
                )
            )
        return ui.TagList(
            ui.a(
                "Login",
                href="#",
                class_="nav-link",
                onclick="Shiny.setInputValue('show_auth_modal', 'login', {priority: 'event'});"
            ),
            ui.a(
                "Register",
                href="#",
                class_="nav-link",
                onclick="Shiny.setInputValue('show_auth_modal', 'register', {priority: 'event'});"
            )
        )
    
    # ---------------------------
    # APPLICATION STATE
    # ---------------------------
     # Reactive calculation for selected proteome data
    @reactive.Calc
    def selected_proteome_data():
        selected = input.proteome_types()
        dfs = []
        
        if "ref" in selected:
            ref_df = data()["ref"].copy()
            ref_df["Proteome Type"] = "Reference"  # Add type column
            dfs.append(ref_df)
            
        if "other" in selected:
            other_df = data()["other"].copy()
            other_df["Proteome Type"] = "Other"  # Add type column
            dfs.append(other_df)
            
        return pd.concat(dfs).reset_index(drop=True) if dfs else pd.DataFrame()

    current_page = reactive.Value(1)
    filtered_data = reactive.Value(pd.DataFrame())
    is_loading = reactive.Value(False)

    
    @reactive.Effect
    @reactive.event(selected_proteome_data)
    def initialize_filtered_data():
        new_data = selected_proteome_data()
        if not new_data.empty:
            filtered_data.set(new_data.copy())
            current_page.set(1)


    # ---------------------------
    # PROTEOME BROWSER LOGIC
    # ---------------------------
    @reactive.Calc
    def filtered_table_data() -> pd.DataFrame:
        df = filtered_data().copy()
        if df.empty:
            return pd.DataFrame()

        # Safely get organism column name (case-insensitive)
        organism_col = next((col for col in df.columns if col.lower() == "organism"), None)
        if organism_col is None:
            print("Warning: No 'Organism' column found in data")
            return pd.DataFrame()

        # Apply taxa list filtering if present
        if input.taxa_list():
            taxa_input = input.taxa_list().strip()
            if taxa_input:
                # Process taxa list
                taxa_list = [taxa.strip().lower() for taxa in taxa_input.split(",") if taxa.strip()]
                mask = pd.Series(False, index=df.index)
                
                # Create combined mask for all taxa
                for taxa in taxa_list:
                    mask |= df[organism_col].str.lower().str.contains(re.escape(taxa), na=False)
                df = df[mask].copy()

        return df

    
    @reactive.Calc
    def page_size():
        return int(input.page_size())

    @reactive.Calc
    def total_pages() -> int:
        return max(1, math.ceil(len(filtered_table_data()) / page_size()))

    @reactive.Effect
    @reactive.event(input.page_size)
    def _():
        current_page.set(1)
    
    @output
    @render.text
    def ref_count_badge():
        count = data()["ref"].shape[0]
        return f" ({count:,})"

    @output
    @render.text
    def other_count_badge():
        count = data()["other"].shape[0]
        return f" ({count:,})"

    @output
    @render.text
    def filtered_proteome_count():
        return f"{filtered_table_data().shape[0]:,}"

    @output
    @render.text
    def protein_coverage():
        filtered = filtered_table_data()
        if 'Protein count' not in filtered.columns:
            return "0"
        return f"{filtered['Protein count'].sum():,}" if not filtered.empty else "0"
    
    def get_column_mappings(df: pd.DataFrame) -> dict:
        """Generate column display mappings based on actual data columns"""
        base_mappings = {
            'Proteome Id': 'Proteome ID',
            'Organism': 'Organism',
            'Protein count': 'Proteins',
            'Proteome Type': 'Proteome Type' 
        }
        
        # Create dynamic mappings for additional columns
        return {
            col: base_mappings.get(col, col.replace('_', ' ').title())
            for col in df.columns
        }

    @output
    @render.data_frame
    def proteome_table():
        if is_loading():
            # Return empty DataFrame with loading message
            empty_df = pd.DataFrame({"Status": ["Loading proteome data..."]})
            return render.DataGrid(
                empty_df,
                filters=False,
                selection_mode="none",
                height="100%",
                width="100%"
            )
        
        data = filtered_table_data()
        if data.empty:
            # Return empty DataFrame with message
            empty_df = pd.DataFrame({"Status": ["No matching proteomes found"]})
            return render.DataGrid(
                empty_df,
                filters=False,
                selection_mode="none",
                height="100%",
                width="100%"
            )
        
        # Apply column mappings
        column_mappings = get_column_mappings(data)
        display_data = data.rename(columns=column_mappings)

        # Truncate and add title attributes for Taxonomic Lineage
        if 'Taxonomic Lineage' in display_data.columns:
            display_data['Taxonomic Lineage'] = display_data['Taxonomic Lineage'].apply(
                lambda x: (x[:50] + '...') if len(x) > 50 else x
            )
            
            # Create formatters dictionary
            formatters = {
                'Taxonomic Lineage': lambda x: {
                    'content': x,
                    'title': data.loc[x.name, 'Taxonomic Lineage']  # Original untruncated value
                }
            }
        else:
            formatters = {}
        
        # Pagination
        start = (current_page() - 1) * page_size()
        end = start + page_size()
        
        return render.DataGrid(
            display_data.iloc[start:end],
            filters=False,
            selection_mode="row",
            height="100%",
            width="100%"
        )

    # Update page status text
    @output
    @render.text
    def page_status():
        return f"Page {current_page()} of {total_pages()} (showing {page_size()} results/page)"

    @reactive.Effect
    @reactive.event(input.next_page)
    def next_page():
        if current_page() < total_pages():
            current_page.set(current_page() + 1)

    @reactive.Effect
    @reactive.event(input.prev_page)
    def prev_page():
        if current_page() > 1:
            current_page.set(current_page() - 1)


    @reactive.Effect
    @reactive.event(input.proteome_types)
    def validate_proteome_selection():
        if not input.proteome_types():
            ui.notification_show(
                "At least one proteome type must be selected!",
                type="warning",
                duration=3
            )

    @reactive.Effect
    @reactive.event(input.apply_filters)
    def apply_filters():

        if not input.proteome_types():
            ui.notification_show("Please select at least one proteome type!", type="error")
            return
    
        is_loading.set(True)
        try:
            with ui.Progress(min=1, max=15) as p:
                p.set(message="Initializing...")
                taxa_list_combined = []
                
                if input.taxa_list():
                    p.set(3, message="Processing text input")
                    taxa_input = input.taxa_list().strip()
                    if taxa_input:
                        taxa_list_combined.extend(
                            [taxa.strip().lower() for taxa in taxa_input.split(",") if taxa.strip()]
                        )
                
                if input.taxa_file() and len(input.taxa_file()) > 0:
                    p.set(6, message="Processing file upload")
                    file: FileInfo = input.taxa_file()[0]
                    try:
                        with open(file["datapath"], "r") as f:
                            content = f.read().splitlines()
                            taxa_list_combined.extend([line.strip().lower() for line in content if line.strip()])
                    except Exception as e:
                        ui.notification_show(f"Error reading file: {str(e)}", type="error")
                
                taxa_list_combined = list(set(taxa_list_combined))

                base_data = selected_proteome_data().copy()
                
                p.set(9, message="Applying filters")
                if not taxa_list_combined:
                    result = base_data
                else:
                    filtered_proteomes = []
                    for i, taxa in enumerate(taxa_list_combined):
                        escaped_taxa = re.escape(taxa)
                        ref_match = base_data[
                            base_data['Organism'].str.contains(escaped_taxa, case=False, na=False)
                        ].copy()
                        
                        if input.remove_redundancy() and not ref_match.empty:
                            ref_match = ref_match.head(1)
                        
                        if not ref_match.empty:
                            filtered_proteomes.append(ref_match)
                        
                        p.set(10 + min(5, int(i/len(taxa_list_combined)*5)), 
                             message=f"Processing {taxa[:20]}{'...' if len(taxa) > 20 else ''}")
                    
                    result = pd.concat(filtered_proteomes).drop_duplicates() if filtered_proteomes else pd.DataFrame()
                
                if not taxa_list_combined and input.remove_redundancy():
                    result = result.drop_duplicates(subset=["Organism"], keep="first")
                
                p.set(15, message="Finalizing results")
                filtered_data.set(result if not result.empty else pd.DataFrame())
                current_page.set(1)
                
        except Exception as e:
            ui.notification_show(f"An error occurred: {str(e)}", type="error")
            filtered_data.set(pd.DataFrame())
        finally:
            is_loading.set(False)


    @render_widget  
    def proteome_pie():
        filtered = filtered_table_data()
        
        # Create minimal empty state when no data
        if filtered.empty:
            fig = px.pie(
                values=[1], 
                names=["No data"],
                hole=0.4
            )
            fig.update_traces(
                textinfo='none',
                marker=dict(colors=['#e9ecef']),  # Changed from 'color' to 'colors'
                hoverinfo='none',
                showlegend=False
            )
            fig.update_layout(
                margin=dict(t=0, b=0, l=0, r=0),
                height=150,
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)'
            )
            return fig
        
        # Check if we have the required columns
        if 'Proteome Type' not in filtered.columns:
            filtered['Proteome Type'] = 'Unknown'
        
        # Process the data
        counts = filtered['Proteome Type'].value_counts()
        counts.index = counts.index.map({'Reference': 'Ref', 'Other': 'Other'})
        
        # Create the pie chart
        fig = px.pie(
            counts,
            values=counts.values,
            names=counts.index,
            color=counts.index,
            color_discrete_map={
                'Ref': '#28a745',
                'Other': '#6c757d'
            },
            hole=0.4
        )
        
        fig.update_traces(
            textposition='outside',
            textinfo='percent+label',
            hovertemplate="<b>%{label}</b><br>Count: %{value}",
            textfont_size=12,
            pull=0.02,
            insidetextorientation='horizontal',
            textfont_color='#333333'
        )
        
        fig.update_layout(
            margin=dict(t=20, b=20, l=40, r=40),
            height=180,
            width=220,
            showlegend=False,
            uniformtext_minsize=10,
            uniformtext_mode='hide',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)'
        )
        
        return fig


    # ---------------------------
    # PROTEOME DOWNLOAD LOGIC
    # ---------------------------

    async def download_proteome_async(session, proteome_id, taxa, retries=RETRIES):
            url = f"https://rest.uniprot.org/uniprotkb/stream?compressed=true&format=fasta&query=proteome:{proteome_id}"
            
            for attempt in range(retries):
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            compressed_data = await response.read()
                            return gzip.decompress(compressed_data).decode("utf-8"), taxa
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    print(f"Attempt {attempt+1} failed for {taxa}: {str(e)}")
                    if attempt == retries - 1:
                        return None, taxa
                    await asyncio.sleep(2 ** attempt)

    async def fetch_fasta_data(matched_df, output_path, progress_callback):
        failed_downloads = []
        
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            tasks = []
            for _, row in matched_df.iterrows():
                tasks.append(
                    download_proteome_async(
                        session,
                        row['Proteome Id'],
                        row['Organism']
                    )
                )

            with open(output_path, 'w', encoding='utf-8') as fasta_file:
                for batch_num in range(0, len(tasks), BATCH_SIZE):
                    batch = tasks[batch_num:batch_num+BATCH_SIZE]
                    results = await asyncio.gather(*batch)
                    
                    for proteome_data, taxa in results:
                        if proteome_data:
                            fasta_file.write(proteome_data)
                        else:
                            failed_downloads.append(taxa)
                            
                        if progress_callback:
                            progress_callback()
                            
                    await asyncio.sleep(1)  # Rate limiting

        if failed_downloads:
            failed_path = os.path.join(os.path.dirname(output_path), "failed_downloads.csv")
            pd.DataFrame({'Failed Taxa': failed_downloads}).to_csv(failed_path)
            return failed_path
        return None

    # Reactive values for download management
    tmp_dir_path = reactive.Value(None)
    download_status = reactive.Value({
        "ready": False, 
        "path": None, 
        "error": None, 
        "failed": None,
        "progress": 0
    })

    @output
    @render.ui
    def download_status_ui():
        status = download_status.get()
        if status["ready"]:
            return ui.download_button("download_fasta", "Download FASTA", class_="btn-success")
        elif status["error"]:
            return ui.div(f"Error: {status['error']}", class_="text-danger")
        else:
            if status["progress"] > 0:
                return ui.div(
                    ui.div(
                        # Child element first
                        ui.div(
                            class_="progress-bar",
                            role="progressbar",
                            style=f"width: {status['progress']}%",
                            aria_valuenow=status["progress"],
                            aria_valuemin="0",
                            aria_valuemax="100"
                        ),
                        # Keyword args after
                        class_="progress",
                        style="height: 20px;"
                    ),
                    ui.div(
                        f"{status['progress']:.1f}% Complete",
                        class_="text-center small mt-1"
                    )
                )
            else:
                return None


    # Modified prepare_download_handler with proper progress reporting
    @reactive.Effect
    @reactive.event(input.prepare_download)
    async def prepare_download_handler():
        try:
            # Clear previous state
            download_status.set({
                "ready": False,
                "path": None,
                "error": None,
                "failed": None,
                "progress": 0
            })

            data = filtered_table_data()
            if data.empty:
                raise ValueError("No proteomes selected for download")

            # Create progress panel
            with ui.Progress(min=1, max=100) as p:
                p.set(message="Preparing FASTA download...", detail="This may take several minutes")

                # Create temp directory
                temp_dir = tempfile.mkdtemp()
                tmp_dir_path.set(temp_dir)
                fasta_path = os.path.join(temp_dir, "proteomes.fasta")

                # Initialize progress tracking
                total = len(data)
                processed = 0
                failed_downloads = []

                async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
                    tasks = []
                    for _, row in data.iterrows():
                        tasks.append(
                            download_proteome_async(
                                session,
                                row['Proteome Id'],
                                row['Organism']
                            )
                        )

                    with open(fasta_path, 'w') as fasta_file:
                        for batch_num in range(0, len(tasks), BATCH_SIZE):
                            batch = tasks[batch_num:batch_num+BATCH_SIZE]
                            results = await asyncio.gather(*batch)
                            
                            for proteome_data, taxa in results:
                                processed += 1
                                progress = min(99, int(processed/max(1,total) * 100)) if total > 0 else 0
                                p.set(progress, message=f"Downloaded {processed}/{total} proteomes")
                                
                                if proteome_data:
                                    fasta_file.write(proteome_data)
                                else:
                                    failed_downloads.append(taxa)
                            
                            await asyncio.sleep(0.1)  # Allow UI updates

                # Handle failures
                if failed_downloads:
                    failed_path = os.path.join(temp_dir, "failed_downloads.csv")
                    pd.DataFrame({'Failed Taxa': failed_downloads}).to_csv(failed_path)
                    # Update status properly
                    download_status.set({
                        **download_status.get(),
                        "failed": failed_path
                    })

                # Final update
                p.set(100, message="Preparation complete!")
                download_status.set({
                    "ready": True,
                    "path": fasta_path,
                    "error": None,
                    "failed": failed_path if failed_downloads else None,  # ADD THIS
                    "progress": 100
                })

        except Exception as e:
            download_status.set({
                "ready": False,
                "path": None,
                "error": str(e),
                "failed": None,
                "progress": 0
            })
            if tmp_dir_path.get():
                shutil.rmtree(tmp_dir_path.get(), ignore_errors=True)
                tmp_dir_path.set(None)

    # Modified download renderer
    @render.download(
    filename=lambda: "proteomes.fasta",
    media_type="text/plain"
    )
    def download_fasta():
        status = download_status.get()
        temp_dir = tmp_dir_path.get()
        
        if not status["ready"] or not temp_dir or not status["path"]:
            raise ValueError("Download not ready")
        
        try:
            # Read and send the actual FASTA content
            with open(status["path"], "r") as f:
                yield f.read()
        except Exception as e:
            raise ValueError(f"Download failed: {str(e)}")
        finally:
            # Cleanup after download completes
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            tmp_dir_path.set(None)
            download_status.set({
                "ready": False,
                "path": None,
                "error": None,
                "failed": None,
                "progress": 0
            })

    # Failed downloads UI
    @render.ui
    def download_failed_ui():
        status = download_status.get()
        failed_path = status.get("failed")  # Use .get() for safe access
        
        if not failed_path or not os.path.exists(failed_path):
            return None
            
        return ui.div(
            ui.tags.i(class_="bi bi-exclamation-triangle text-warning me-2"),
            ui.span("Some downloads failed!", class_="text-warning"),
            ui.download_link(
                id="download_failed_report",
                label="Download failure report",
                class_="ms-2"
            ),
            class_="mt-2"
        )

    @render.download(filename=lambda: "failed_downloads.csv")  # No id parameter
    def download_failed_report():  # Name matches UI component id
        status = download_status.get()
        if status["failed"] and os.path.exists(status["failed"]):
            with open(status["failed"], "rb") as f:
                yield f.read()


    # ---------------------------
    # HPC MANAGEMENT
    # ---------------------------
    ssh_client = reactive.Value(None)
    current_dir = reactive.Value("~")
    hpc_connected = reactive.Value(False)
    hpc_output_log = reactive.Value("Waiting for command output...")

    selected_file = reactive.Value(None)
    file_content = reactive.Value("")
    editor_visible = reactive.Value(False)
    selected_hpc_item = reactive.Value(None)
    hpc_refresh_trigger = reactive.Value(0)
    
    available_modules = reactive.Value([])
    selected_modules = reactive.Value([])
    modules_loading = reactive.Value(False)
    job_queue_df = reactive.Value(pd.DataFrame())
    


    @reactive.Effect
    @reactive.event(input.hpc_connect)
    async def connect_hpc():
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            with ui.Progress(min=1, max=3) as p:
                p.set(message="Connecting...")
                client.connect(
                    input.hpc_host(),
                    username=input.hpc_user(),
                    password=input.hpc_pass(),
                    timeout=10
                )
                p.set(2, message="Verifying connection...")
                stdin, stdout, stderr = client.exec_command("echo $HOME")
                home_path = stdout.read().decode().strip()
                current_dir.set(home_path)
                ssh_client.set(client)
                hpc_connected.set(True)
                p.set(3, message="Connected!")
                ui.notification_show("HPC connection established", type="message")
                
        except Exception as e:
            ui.notification_show(f"Connection failed: {str(e)}", type="error")
            ssh_client.set(None)
            hpc_connected.set(False)

    @reactive.Effect
    @reactive.event(input.hpc_disconnect)
    def disconnect_hpc():
        """Handle HPC disconnection"""
        client = ssh_client.get()
        if client is not None:
            try:
                client.close()
                ui.notification_show("Disconnected from HPC", type="message")
            except Exception as e:
                ui.notification_show(f"Error disconnecting: {str(e)}", type="error")
            finally:
                ssh_client.set(None)
                hpc_connected.set(False)
                current_dir.set("~")
                hpc_refresh_trigger.set(hpc_refresh_trigger() + 1)
        else:
            ui.notification_show("Not connected to HPC", type="warning")

    @reactive.Calc
    def get_hpc_files():

        hpc_refresh_trigger()

        if not hpc_connected():
            return pd.DataFrame()
        
        try:
            stdin, stdout, stderr = ssh_client().exec_command(
                f"ls -l {current_dir()} | awk 'NR>1 {{print $0}}'"
            )
            output = stdout.read().decode()
            lines = output.splitlines()
            
            parsed = []
            if current_dir() != "/":
                parsed.append({
                    'name': '..',
                    'type': 'Directory',
                    'size': '',
                    'owner': '',
                    'perms': 'drwxr-xr-x'
                })

            for line in lines:
                parts = line.split()
                if len(parts) >= 9:
                    name = ' '.join(parts[8:])
                    if name.startswith('.'):
                        continue
                    
                    file_type = 'Directory' if parts[0].startswith('d') else 'File'
                    parsed.append({
                        'name': name,
                        'type': file_type,
                        'size': parts[4],
                        'owner': parts[2],
                        'perms': parts[0]
                    })

            return pd.DataFrame(parsed)
        
        except Exception as e:
            ui.notification_show(f"Error listing directory: {str(e)}", type="error")
            return pd.DataFrame()


    @output
    @render.data_frame
    def hpc_file_browser():
        df = get_hpc_files()
        if df.empty:
            return None
        
        display_df = df.copy()
        display_df['display_name'] = display_df.apply(
            lambda row: f"📁 {row['name']}" if row['type'] == 'Directory' else row['name'],
            axis=1
        )

        def style_func(data):
            return [{
                'rows': [i for i, row in data.iterrows() if row['type'] == 'Directory'],
                'class': 'directory'
            }]

        return render.DataGrid(
            display_df[['display_name', 'type', 'size', 'owner', 'perms']],
            width="100%",
            height="100%",
            selection_mode="row",
            summary=False,
            filters=False,
            styles=style_func,
        )

    @reactive.Effect
    @reactive.event(input.hpc_execute)
    async def execute_command():
        if not hpc_connected():
            ui.notification_show("Not connected to HPC", type="warning")
            return
            
        cmd = input.hpc_command().strip()
        if not cmd:
            return
            
        try:
            with ui.Progress() as p:
                p.set(message="Executing command...")
                # Execute command in current directory
                full_cmd = f"cd {current_dir()} && bash -l -c '{cmd}'"
                stdin, stdout, stderr = ssh_client().exec_command(full_cmd)
                
                output = stdout.read().decode()
                error = stderr.read().decode()
                
                # Update output log
                new_content = f"$ {full_cmd}\n{output}{error}"
                hpc_output_log.set(hpc_output_log.get() + "\n\n" + new_content)

                # Clear the input after successful execution
                await session.send_custom_message("clear_hpc_command", {})
                
                if error:
                    ui.notification_show(f"Command error: {error}", type="warning")
                
                p.set(1, message="Command completed")
                
        except Exception as e:
            ui.notification_show(f"Execution failed: {str(e)}", type="error")

    @output
    @render.text
    def hpc_output():
        return hpc_output_log.get()

    # File Transfer
    @reactive.Effect
    @reactive.event(input.hpc_transfer)
    async def transfer_files():
        if not hpc_connected():
            ui.notification_show("Not connected to HPC", type="warning")
            return
            
        files = input.hpc_upload()
        if not files:
            return
            
        try:
            with ui.Progress() as p:
                p.set(message="Initiating transfer...")
                with SCPClient(ssh_client().get_transport()) as scp:
                    for i, file in enumerate(files):
                        p.set(i/len(files), message=f"Uploading {file['name']}")
                        # Preserve original filename in remote path
                        remote_path = os.path.join(current_dir(), file["name"])
                        scp.put(file["datapath"], remote_path=remote_path)
                ui.notification_show("File transfer completed", type="message")
                hpc_refresh_trigger.set(hpc_refresh_trigger() + 1)

                
        except Exception as e:
            ui.notification_show(f"Transfer failed: {str(e)}", type="error")

    # Current Directory Display
    @output
    @render.ui
    def hpc_pwd():
        if not hpc_connected():
            return ""
        return ui.div(
            ui.tags.strong("Current directory: "),
            ui.tags.code(current_dir()),
            class_="mb-2 text-muted"
        )
    
    
    @reactive.Effect
    @reactive.event(input.hpc_refresh)
    def refresh_hpc_listing():
        """Force refresh of HPC file browser"""
        hpc_refresh_trigger.set(hpc_refresh_trigger() + 1)

    @reactive.Effect
    @reactive.event(input.hpc_file_browser_selected_rows)
    def handle_selection():
        """Handle file/directory selection without automatic content loading"""
        try:
            df = get_hpc_files()
            selected = input.hpc_file_browser_selected_rows()
            
            if not selected or df.empty:
                selected_hpc_item.set(None)
                editor_visible.set(False)
                return

            selected_idx = selected[0]
            if 0 <= selected_idx < len(df):
                selected_row = df.iloc[selected_idx].to_dict()
                selected_hpc_item.set(selected_row)
                # No automatic content loading here

        except Exception as e:
            ui.notification_show(f"Selection error: {str(e)}", type="error")

    @reactive.Effect
    @reactive.event(current_dir)
    async def reset_selection():
        """Enhanced directory change handler"""
        try:
            # Clear UI selection
            await session.send_custom_message(
                "update-shiny-data-grid",
                {
                    "id": "hpc_file_browser",
                    "action": "updateSelectedRows",
                    "selectedRows": []
                }
            )
            # Reset file-related states
            selected_hpc_item.set(None)
            editor_visible.set(False)
            file_content.set("")
            
        except Exception as e:
            print(f"Error resetting selection: {str(e)}")


    # Add this modal UI component in your server function
    def file_editor_modal():
        return ui.modal(
            ui.div(
                ui.div(
                    ui.span("File Editor", class_="h4"),
                    ui.div(
                        ui.input_action_link(
                            "close_editor",
                            ui.tags.i(class_="bi bi-x-lg"),
                            class_="btn btn-sm text-danger",
                            title="Close editor"
                        ),
                        class_="float-end"
                    ),
                    class_="d-flex justify-content-between align-items-center mb-3 p-3 border-bottom",
                    style="height: 60px; flex-shrink: 0;"
                ),
                ui.div(
                    ui.input_text_area(
                        "file_editor", 
                        "", 
                        value=file_content.get(),
                        height="70vh",
                        width="100%"
                    ),
                    class_="custom-editor-container",
                    style=(
                        "border: none; "
                        "background: transparent; "
                        "padding: 0.75rem; "
                        "overflow: auto; "
                        "max-height: 80vh;")
                ),
                ui.div(
                    ui.input_action_button(
                        "save_file", 
                        "Save Changes", 
                        class_="btn-success float-end"
                    ),
                    class_="p-3 border-top"
                ),
                class_="bg-white rounded-3",
                style=(
                    "min-width: 90vw; "
                    "width: 90vw; "
                    "position: fixed; "
                    "top: 50%; "
                    "left: 50%; "
                    "transform: translate(-50%, -50%); "
                    "max-height: 90vh; "
                    "overflow: hidden; "
                    "display: flex; "
                    "flex-direction: column;"
                )
            ),
            easy_close=True,
            footer=None,
            size='l',
            class_="p-0 show d-block",
            style=(
                "overflow: hidden !important; "
                "background-color: rgba(0,0,0,0.5) !important;"
            )
        )



    # 2. Close editor handlers
    @reactive.Effect
    @reactive.event(input.close_editor)
    def close_editor_handler():
        """Close the editor modal"""
        ui.modal_remove()

    @reactive.Effect
    @reactive.event(current_dir, input.hpc_file_browser_selected_rows)
    def auto_close_editor():
        """Close editor when directory changes or selection changes"""
        ui.modal_remove()

    @reactive.Effect
    @reactive.event(input.hpc_open)
    def handle_open_action():
        """Handle open action for both directories and files"""
        item = selected_hpc_item.get()
        if not item:
            return
        
        try:
            if item['type'] == 'Directory':
                # Directory navigation logic
                current_path = current_dir().rstrip('/')
                target_name = item['name']
                
                # Calculate new path
                new_path = os.path.normpath(
                    os.path.join(current_path, target_name) 
                    if target_name != '..' 
                    else os.path.dirname(current_path)
                )

                # Validate and update directory
                stdin, stdout, stderr = ssh_client().exec_command(f'[ -d "{new_path}" ]')
                if stdout.channel.recv_exit_status() == 0:
                    current_dir.set(new_path)
                    hpc_refresh_trigger.set(hpc_refresh_trigger() + 1)
                else:
                    ui.notification_show(f"Invalid directory: {new_path}", type="warning")
                    
            else:
                # File handling logic
                if handle_file_content(item):
                    ui.modal_show(file_editor_modal())

        except Exception as e:
            ui.notification_show(f"Open action failed: {str(e)}", type="error")

    def handle_file_content(selected_row):
        """Handle file content loading with limited display for large files"""
        try:
            filename = selected_row['name']
            full_path = os.path.join(current_dir(), filename)
            
            # File size check
            stdin, stdout, stderr = ssh_client().exec_command(f"stat -c%s '{full_path}'")
            file_size = int(stdout.read().decode().strip())
            
            # Display parameters
            MAX_DISPLAY_SIZE = 5000000  # ~50KB
            MAX_LINES = 50000  # Maximum lines to display
            TRUNCATE_MESSAGE = "\n\n[TRUNCATED - FILE TOO LARGE TO DISPLAY FULLY]"
            
            if file_size > MAX_DISPLAY_SIZE:
                ui.notification_show(
                    "Large file detected - showing first portion only",
                    type="warning",
                    duration=5
                )
                
                # Get first portion efficiently
                stdin, stdout, stderr = ssh_client().exec_command(
                    f"head -n {MAX_LINES} '{full_path}' | head -c {MAX_DISPLAY_SIZE}"
                )
                content = stdout.read().decode('utf-8', errors='replace')
                
                # Add truncation message if we didn't get the whole file
                if len(content) >= MAX_DISPLAY_SIZE:
                    content = content[:MAX_DISPLAY_SIZE] + TRUNCATE_MESSAGE
            else:
                # Small file - read normally
                stdin, stdout, stderr = ssh_client().exec_command(f"cat '{full_path}'")
                content = stdout.read().decode('utf-8', errors='replace')
            
            file_content.set(content)
            return True
            
        except Exception as e:
            ui.notification_show(f"File handling error: {str(e)}", type="error")
            return False


    def load_file_content(filename):
        try:
            full_path = os.path.join(current_dir(), filename)
            stdin, stdout, stderr = ssh_client().exec_command(f"cat '{full_path}'")
            content = stdout.read().decode()
            # Check for read errors
            if stderr.channel.recv_exit_status() != 0:
                raise Exception(stderr.read().decode())
            file_content.set(content)
        except Exception as e:
            ui.notification_show(f"Error loading file: {str(e)}", type="error")
            # Explicitly hide editor on load failure
            editor_visible.set(False)
            file_content.set("")



    @reactive.Effect
    @reactive.event(input.save_file)
    def save_file_changes():
        if selected_hpc_item.get() is None:
            return
        
        try:
            filename = selected_hpc_item.get()['name']
            full_path = posixpath.join(current_dir(), filename)
            
            # Create temporary file with content
            temp_path = os.path.join(tempfile.gettempdir(), filename)
            with open(temp_path, 'w') as f:
                f.write(input.file_editor())
            
            # Upload the modified file
            with ssh_client().open_sftp() as sftp:
                sftp.put(temp_path, full_path)
            
            os.remove(temp_path)
            ui.notification_show("File saved successfully", type="message")
        except Exception as e:
            ui.notification_show(f"Error saving file: {str(e)}", type="error")

    @reactive.Effect
    @reactive.event(input.hpc_delete)
    def delete_selected_item():
        item = selected_hpc_item.get()
        if not item:
            return
        
        try:
            full_path = os.path.join(current_dir(), item['name'])
            if item['type'] == 'Directory':
                cmd = f"rm -rf '{full_path}'"
            else:
                cmd = f"rm '{full_path}'"
                
            stdin, stdout, stderr = ssh_client().exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            
            if exit_status == 0:
                ui.notification_show(f"Deleted {item['name']}", type="message")
                hpc_refresh_trigger.set(hpc_refresh_trigger() + 1)
                selected_hpc_item.set(None)
            else:
                error = stderr.read().decode()
                ui.notification_show(f"Deletion failed: {error}", type="error")
                
        except Exception as e:
            ui.notification_show(f"Deletion error: {str(e)}", type="error")



    @render.download(
        filename=lambda: selected_hpc_item.get()["name"] + (
            ".zip" if selected_hpc_item.get() and selected_hpc_item.get()["type"] == "Directory" 
            else ""
        )
    )
    def hpc_download_handler():
        """Handles HPC file/directory downloads"""
        item = selected_hpc_item.get()
        if not item:
            raise ValueError("No item selected for download")
        
        try:
            item_name = item["name"]
            full_path = posixpath.join(current_dir(), item_name)
            
            with tempfile.TemporaryDirectory() as tmpdir:
                if item["type"] == "File":
                    local_path = os.path.join(tmpdir, item_name)
                    with ssh_client().open_sftp() as sftp:
                        sftp.get(full_path, local_path)
                    with open(local_path, "rb") as f:
                        yield f.read()
                
                elif item["type"] == "Directory":
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                        with ssh_client().open_sftp() as sftp:
                            def add_to_zip(path):
                                for entry in sftp.listdir_attr(path):
                                    remote_path = posixpath.join(path, entry.filename)
                                    if stat.S_ISDIR(entry.st_mode):
                                        add_to_zip(remote_path)
                                    else:
                                        with sftp.file(remote_path, "rb") as remote_file:
                                            zipf.writestr(
                                                posixpath.relpath(remote_path, full_path),
                                                remote_file.read()
                                            )
                            add_to_zip(full_path)
                    yield zip_buffer.getvalue()
        
        except Exception as e:
            ui.notification_show(f"Download failed: {str(e)}", type="error")
            raise


    @reactive.Effect
    @reactive.event(input.refresh_queue, hpc_connected)
    def update_slurm_queue():
        """Refresh the Slurm job queue display"""
        if not hpc_connected():
            job_queue_df.set(pd.DataFrame())
            return

        user = input.hpc_user()
        if not user:
            job_queue_df.set(pd.DataFrame())
            return

        try:
            # Get formatted job queue output
            stdin, stdout, stderr = ssh_client().exec_command(
                f"squeue -u {user} --format='%A|%j|%T|%M'"
            )
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()
            
            if error:
                print(f"Queue error: {error}")
                job_queue_df.set(pd.DataFrame())
                return

            # Parse the output into DataFrame
            if not output:
                job_queue_df.set(pd.DataFrame())
                return

            rows = [line.split("|") for line in output.split("\n")]
            df = pd.DataFrame(rows[1:], columns=rows[0])
            df = df[["JOBID", "NAME", "STATE", "TIME"]]
            df.columns = ["Job ID", "Name", "Status", "Time"]
            job_queue_df.set(df)

        except Exception as e:
            print(f"Queue update failed: {str(e)}")
            job_queue_df.set(pd.DataFrame())

    
    @output
    @render.data_frame
    def job_queue_table():
        df = job_queue_df.get()
        if df.empty:
            return render.DataGrid(
                pd.DataFrame([{"Status": "No jobs in queue"}]),
                height="150px",
                width="100%"
            )
        
        return render.DataGrid(
            df,
            height="250px",
            width="100%",
            filters=False,
            summary=False,
            selection_mode="none"
        )
    

    @reactive.Effect
    @reactive.event(input.create_job)
    def _():
        if hpc_connected():
            load_modules()
    

    @reactive.Effect
    @reactive.event(input.create_job)
    def show_job_creator():
        if not hpc_connected():
            ui.notification_show("Connect to HPC first!", type="error")
            return

        ui.modal_show(
            ui.modal(
                ui.div(
                    # Header
                    ui.div(
                        ui.span("SLURM Job Configuration", class_="h4"),
                        ui.div(
                            ui.input_action_link(
                                "modal_close",
                                ui.tags.i(class_="bi bi-x-lg"),
                                data_bs_dismiss="modal",
                                class_="btn btn-sm text-danger",
                                title="Close"
                            ),
                            class_="float-end"
                        ),
                        class_="d-flex justify-content-between align-items-center mb-3 p-3 border-bottom",
                        style="height: 60px; flex-shrink: 0;"
                    ),

                    # Scrollable Modal Body
                    ui.div(
                        ui.div(
                            ui.layout_columns(
                                # Column 1
                                ui.div(
                                    ui.card(
                                        ui.card_header(
                                            ui.tags.i(class_="bi bi-gear me-2"),
                                            "Basic Settings",
                                            class_="text-success fw-bold fs-6"
                                        ),
                                        ui.div(
                                            ui.input_text("job_name", "Job Name", placeholder="Analysis Job", width="100%"),
                                            ui.layout_columns(
                                                ui.div(ui.input_numeric("job_nodes", "Nodes", value=1, min=1), class_="compact-input"),
                                                ui.div(ui.input_numeric("job_cpus", "CPUs", value=4, min=1), class_="compact-input"),
                                                ui.div(ui.input_text("job_mem", "Memory", value="8G"), class_="compact-input"),
                                                ui.div(ui.input_text("job_time", "Time Limit", value="01:00:00"), class_="compact-input"),
                                                col_widths=(3, 3, 3, 3),
                                                class_="g-2 mb-3"
                                            ),
                                            ui.input_selectize(
                                                "job_partition", "Partition", choices=[], width="100%",
                                                options={"placeholder": "Select partition...", "persist": False}
                                            ),
                                            class_="p-2"
                                        ),
                                        class_="border-success h-100"
                                    ),
                                    class_="h-100"
                                ),

                                # Column 2
                                ui.div(
                                    ui.card(
                                        ui.card_header(
                                            ui.tags.i(class_="bi bi-terminal me-2"),
                                            "Execution Environment",
                                            class_="text-success fw-bold fs-6"
                                        ),
                                        ui.div(
                                            ui.input_text("working_dir", "Working Directory", value="/home/$USER/", width="100%"),
                                            ui.div(
                                                ui.div(
                                                    ui.tags.i(class_="bi bi-box-seam me-2"),
                                                    ui.span("Software Modules", class_="text-success fw-bold fs-6"),
                                                    class_="d-flex align-items-center mt-3 mb-2"
                                                ),
                                                ui.layout_columns(
                                                    ui.input_selectize(
                                                        "module_select", None, choices={}, width="100%",
                                                        options={"placeholder": "Search modules...", "maxOptions": 1000}
                                                    ),
                                                    ui.input_action_button(
                                                        "add_module",
                                                        ui.span(ui.tags.i(class_="bi bi-plus-lg"), role="img", aria_label="Add module"),
                                                        class_="btn-success p-1 btn-sm", title="Add module"
                                                    ),
                                                    col_widths=(10, 2),
                                                    class_="g-2 align-items-center"
                                                ),
                                                ui.output_ui("selected_modules_ui"),
                                                class_="mt-3"
                                            ),
                                            class_="p-2"
                                        ),
                                        class_="border-success h-100"
                                    ),
                                    class_="h-100"
                                ),

                                # Column 3
                                ui.div(
                                    ui.card(
                                        ui.card_header(
                                            ui.tags.i(class_="bi bi-envelope me-2"),
                                            "Notifications",
                                            class_="text-success fw-bold fs-6"
                                        ),
                                        ui.div(
                                            ui.input_checkbox("enable_email", "Enable Email Alerts", True),
                                            ui.panel_conditional(
                                                "input.enable_email",
                                                ui.div(
                                                    ui.input_text("job_email", "Email Address", placeholder="user@example.com", width="100%"),
                                                    ui.input_checkbox_group(
                                                        "mail_type", "Notify On:",
                                                        {"BEGIN": "Start", "END": "End", "FAIL": "Failure"},
                                                        selected=["BEGIN", "END", "FAIL"], inline=True
                                                    ),
                                                    class_="ms-3 border-start ps-3"
                                                )
                                            ),
                                            class_="p-2"
                                        ),
                                        class_="border-success h-100"
                                    ),
                                    class_="h-100"
                                ),
                                col_widths=(4, 5, 3),
                                class_="g-3"
                            ),

                            # Job Commands Card
                            ui.card(
                                ui.card_header(
                                    ui.tags.i(class_="bi bi-code me-2"),
                                    "Job Commands",
                                    class_="text-success fw-bold fs-6"
                                ),
                                ui.div(
                                    ui.input_text_area(
                                        "job_commands",
                                        None,
                                        placeholder="# Your commands here\n\n# Example:\npython your_script.py\n",
                                        height="300px", width="100%"
                                    ),
                                    class_="p-2 code-editor"
                                ),
                                class_="border-success mt-3"
                            ),
                            class_="p-3"
                        ),
                        class_="modal-body p-0",
                        style="overflow-y: auto; flex-grow: 1;"
                    ),

                    # Sticky Footer
                    ui.div(
                        ui.input_action_button("submit_job", "Submit Job", class_="btn-success w-100"),
                        class_="p-3 border-top"
                    ),

                    class_="bg-white rounded-3",
                    style=(
                        "min-width: 90vw; width: 90vw; "
                        "position: fixed; top: 50%; left: 50%; "
                        "transform: translate(-50%, -50%); "
                        "max-height: 90vh; overflow: hidden; "
                        "display: flex; flex-direction: column;"
                    )
                ),
                easy_close=True,
                footer=None,
                size="l",
                class_="p-0 show d-block",
                style="overflow: hidden !important; background-color: rgba(0,0,0,0.5) !important;"
            )
        )




    @output
    @render.ui
    def modules_loading_ui():
        if modules_loading.get():
            return ui.div(
                ui.tags.div(
                    ui.tags.span(class_="spinner-border spinner-border-sm"),
                    " Loading modules...",
                    class_="text-muted small"
                ),
                class_="position-absolute top-50 start-50 translate-middle"
            )
        return None

    def load_modules():
        try:
            modules_loading.set(True)
            stdin, stdout, stderr = ssh_client().exec_command(
                "bash -l -c 'module -t avail 2>&1'"
            )
            raw_output = stdout.read().decode()
            
            # Improved module parsing
            modules = []
            for line in raw_output.splitlines():
                # Match modules in format "module/version" or "module"
                if re.match(r"^\w+[/\w.-]*$", line):
                    modules.append(line.strip())
            
            available_modules.set(sorted(modules))
            
        except Exception as e:
            ui.notification_show(f"Module load failed: {str(e)}", type="error")
            available_modules.set([])
        finally:
            modules_loading.set(False)


    @reactive.Calc
    def module_choices():
        return {mod: mod for mod in available_modules.get()} 

    @reactive.Effect
    @reactive.event(input.add_module)
    def add_selected_module():
        module = input.module_select()
        if module and module not in selected_modules.get():
            selected_modules.set([*selected_modules.get(), module])

    @reactive.Effect
    @reactive.event(input.module_to_remove)
    def _():
        module = input.module_to_remove()
        if module and module in selected_modules.get():
            selected_modules.set([m for m in selected_modules.get() if m != module])

    @output
    @render.ui
    def selected_modules_ui():
        modules = selected_modules.get()
        if not modules:
            return ui.span("No modules selected", class_="text-muted")
        
        return ui.TagList(
            ui.h5("Selected Modules:", class_="mt-3"),
            ui.div(
                [
                    ui.span(
                        module,
                        ui.tags.a(
                            ui.tags.i(class_="bi bi-x ms-2"),
                            href="#",
                            class_="text-danger",
                            # Fix JavaScript escaping
                            onclick=f"Shiny.setInputValue('module_to_remove', {json.dumps(module)})"
                        ),
                        class_="badge bg-success me-2 mb-2"
                    )
                    for module in modules
                ],
                class_="d-flex flex-wrap"
            )
        )


    
    @output
    @render.ui
    def module_select_ui():
        return ui.input_selectize(
            "module_select",
            "Available Modules",
            choices=module_choices(),
            selected=None,
            width="100%",
            options={
                "maxOptions": 1000,
                "placeholder": "Type to search modules...",
                "persist": False
            }
        )

    @reactive.Effect
    @reactive.event(available_modules)
    def _():
        # Force refresh Selectize when modules update
        ui.update_selectize(
            "module_select",
            choices=module_choices(),
            selected=None
        )


    @reactive.Effect
    @reactive.event(input.submit_job)
    def handle_job_submission():
        try:
            # Get user-specific working directory
            user = input.hpc_user()
            working_dir = input.working_dir().replace("$USER", user)
            remote_dir = shlex.quote(working_dir)
            
            # Create directory with parents using shell command
            mkdir_cmd = f"mkdir -p {remote_dir}"
            stdin, stdout, stderr = ssh_client().exec_command(mkdir_cmd)
            if stderr.read().decode():
                raise RuntimeError(f"Directory creation failed: {stderr.read().decode()}")
            
            # Handle email notifications
            mail_lines = []
            if input.enable_email():
                email = input.job_email().strip()
                if email:
                    mail_lines.append(f"#SBATCH --mail-user={shlex.quote(email)}")
                    selected_types = input.mail_type()
                    if selected_types:
                        mail_types = ",".join(selected_types)
                        mail_lines.append(f"#SBATCH --mail-type={mail_types}")

            # Clean partition name (remove any display annotations)
            raw_partition = input.job_partition()
            clean_partition = raw_partition.split(" (default)")[0].strip()

            # Create script content with proper indentation
            script_content = f"""#!/bin/bash
#SBATCH --job-name={shlex.quote(input.job_name())}
#SBATCH --partition={shlex.quote(clean_partition)}
#SBATCH --nodes={input.job_nodes()}
#SBATCH --ntasks={input.job_cpus()}
#SBATCH --time={shlex.quote(input.job_time())}
#SBATCH --mem={shlex.quote(input.job_mem())}
#SBATCH --output={remote_dir}/{input.job_name()}-%j.out
#SBATCH --error={remote_dir}/{input.job_name()}-%j.err
{"\n".join(mail_lines)}

cd {remote_dir}

{"module load " + " ".join(map(shlex.quote, selected_modules.get())) if selected_modules.get() else ""}

{input.job_commands()}
"""

            # Write to local temp file
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
                f.write(script_content)
                local_path = f.name

            # Upload script
            remote_path = f"{remote_dir}/{shlex.quote(input.job_name())}.sh"
            with ssh_client().open_sftp() as sftp:
                sftp.put(local_path, remote_path)
                sftp.chmod(remote_path, 0o755)

            # Submit job and capture full output
            stdin, stdout, stderr = ssh_client().exec_command(f"sbatch {shlex.quote(remote_path)}")
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()

            if not output:
                raise RuntimeError(f"No output from sbatch. Error: {error}")
                
            if "Submitted batch job" in output:
                ui.modal_remove()
                ui.notification_show(
                    f"Job submitted successfully! ID: {output.split()[-1]}", 
                    type="message"
                )
                # Trigger file browser refresh
                hpc_refresh_trigger.set(hpc_refresh_trigger() + 1)
                
            else:
                raise RuntimeError(f"Submission failed. Output: {output} | Error: {error}")

        except Exception as e:
            error_msg = f"""Job submission failed: {str(e)}
            
            Debug Information:
            - Partition: {input.job_partition()}
            - Clean Partition: {clean_partition if 'clean_partition' in locals() else 'N/A'}
            - Working Directory: {remote_dir}
            - Modules: {selected_modules.get()}
            - Commands: {input.job_commands()[:200]}
            """
            
            ui.notification_show(
                error_msg,
                duration=15,
                type="error",
                close_button=True
            )
            print(f"Submission Error: {traceback.format_exc()}")
            
        finally:
            if 'local_path' in locals() and os.path.exists(local_path):
                os.remove(local_path)

    def get_hpc_partitions():
        """Get available partitions from HPC with proper header handling"""
        try:
            if not ssh_client.get() or not hpc_connected.get():
                return [], ""

            # Get partition info with header
            stdin, stdout, stderr = ssh_client().exec_command(
                "bash -l -c 'sinfo --format=\"%P\"'"
            )
            raw_output = stdout.read().decode().strip()
            
            # Parse output while handling header
            if raw_output:
                lines = raw_output.split('\n')
                partitions = []
                default = ""
                
                # Skip header line (index 0), process others
                for line in lines[1:]:
                    for part in line.split(','):
                        clean_part = part.strip()
                        if clean_part:
                            # Handle default marker and store
                            if '*' in clean_part:
                                clean_part = clean_part.replace('*', '')
                                if not default:  # First starred is default
                                    default = clean_part
                            partitions.append(clean_part)
                
                # Remove duplicates and sort
                partitions = sorted(list(set(partitions)))
                
                # Set default if not found
                if not default and partitions:
                    default = partitions[0]
                
                return partitions, default

            return [], ""

        except Exception as e:
            print(f"Partition detection failed: {str(e)}")
            return [], ""
        
    @reactive.Effect
    @reactive.event(input.create_job)
    def update_partition_list_on_modal_open():
        try:
            if not hpc_connected():
                return

            partitions, default = get_hpc_partitions()
            
            if not partitions:
                return

            # Create choices with (default) annotation
            choices = {
                p: f"{p} (default)" if p == default else p
                for p in partitions
            }

            ui.update_selectize(
                "job_partition",
                choices=choices,
                selected=default
            )

        except Exception as e:
            print(f"Partition update failed: {str(e)}")


app = App(app_ui, server)

import webbrowser
import threading

def open_browser():
    webbrowser.open_new("http://localhost:8000")

if __name__ == "__main__":
    threading.Timer(1.0, open_browser).start()
    app.run()