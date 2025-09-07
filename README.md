# Mercor Airtable Automation System

This project provides a complete, automated workflow for processing contractor applications using Airtable, Python, and the Google Gemini LLM. It handles data compression, automated shortlisting, and AI-powered enrichment.

For detailed, in-depth information on the architecture, setup, and customization, please see the full [**System Documentation**](./documentation.md).

## Features
- **Data Compression:** Consolidates multi-table Airtable data into a single, full-fidelity JSON object.
- **Data Decompression:** Syncs edits from the JSON object back to the normalized Airtable tables.
- **Automated Shortlisting:** Applies business logic to automatically identify and flag top candidates.
- **LLM Enrichment:** Uses Google's Gemini to provide a qualitative summary, score, and sanity check for each application.

## Tech Stack
- **Database:** Airtable
- **Automation:** Python 3
- **AI:** Google Gemini
- **Key Python Libraries:** `pyairtable`, `google-generativeai`, `python-dotenv`

## Setup and Installation

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd mercor_automation
    ```

2.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: .\venv\Scripts\activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment Variables:**
    -   Make a copy of the `.env.sample` file and rename it to `.env`.
    -   Add your Airtable API Key, Base ID, and Google API Key to the `.env` file.

5.  **Set Up Airtable:**
    -   Set up your Airtable base with the 5-table schema. For a detailed guide to the required fields and types, please refer to the main [System Documentation](https://docs.google.com/document/d/1p3915MDNV_dimTFCrDj2X_RRr4jUkXq1NHlQNOIu25I/edit?usp=sharing).

## Usage
The system is controlled by two main scripts.

-   **To process a new applicant (compress, shortlist, and enrich):**
    ```bash
    # Edit the target_applicant_id at the bottom of main.py
    python main.py
    ```

-   **To sync edits from the JSON back to the tables:**
    ```bash
    # Edit the target_applicant_id at the bottom of decompress.py
    python decompress.py
    ```