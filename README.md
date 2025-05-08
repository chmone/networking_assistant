# Networking Assistant

A Python application designed to assist with professional networking by scraping job postings and potential leads from various sources, processing the data, storing it, and providing access via a web API.

## Features

*   Scrapes job postings from Greenhouse and Lever job boards.
*   Scrapes potential leads (alumni, PMs) from LinkedIn via SerpApi (Google Search).
*   Cleans and processes scraped data.
*   Scores and filters potential leads based on configurable criteria (e.g., location, keywords).
*   Stores company, job posting, and lead information in a database (SQLite by default).
*   Provides a FastAPI web API to interact with the stored data (CRUD operations for Leads, Companies, Jobs).
*   Includes retry logic for robust API interactions.
*   Configurable via environment variables (`.env` file).

## Tech Stack

*   Python 3.12+
*   FastAPI (for Web API)
*   SQLAlchemy (for Database ORM)
*   SQLite (default database)
*   Requests (for HTTP calls)
*   Pydantic (for data validation/schemas)
*   Pytest (for testing)
*   SerpApi (via Google Search for LinkedIn scraping)

## Setup

### Prerequisites

*   Python 3.12 or later
*   pip (Python package installer)
*   Git

### 1. Clone the Repository

```bash
git clone https://github.com/chmone/networking_assistant.git
cd networking_assistant
```

### 2. Install Dependencies

It's recommended to use a virtual environment:

```bash
# Create a virtual environment (optional but recommended)
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 3. Environment Variables

The application uses environment variables for configuration, managed by `src/config/config_manager.py`.

1.  Copy the example environment file:
    ```bash
    cp .env.example .env
    ```
2.  Edit the `.env` file and provide the necessary values, especially:
    *   `SCRAPING_API_KEY`: Your API key for SerpApi (required for LinkedIn scraping).
    *   `DB_PATH`: Path to the database file (defaults to `sqlite:///leads.db` in the project root if not set).
    *   `GREENHOUSE_TOKENS_JSON_PATH`: Path to a JSON file containing Greenhouse board tokens if using the Greenhouse scraper. See `ConfigManager` for format.
    *   Other variables as needed (check `src/config/config_manager.py` and `.env.example` for details like target schools, PM keywords, cache expiry etc.).

### 4. Database Setup

The application uses SQLAlchemy and will create the SQLite database file specified by `DB_PATH` (or the default `leads.db`) if it doesn't exist when the application or `DatabaseManager` is first initialized. No manual schema creation is typically required for SQLite.

## Running the Application

### Option 1: Run the Core Orchestration (Scraping & Processing)

The main orchestration logic likely resides in `main.py` (or needs to be developed there) using `src/core/orchestrator.py`.

```bash
# Example (assuming main.py implements the orchestrator logic)
python main.py
```
*(Note: The specific implementation in `main.py` might need review or creation to fully utilize the orchestrator.)*

### Option 2: Run the Web API

The FastAPI application provides endpoints to interact with the data.

```bash
uvicorn src.web_app.api_main:app --reload --host 0.0.0.0 --port 8000
```

The API documentation (Swagger UI) will be available at `http://localhost:8000/docs`.

## Running Tests

The project uses `pytest` for testing.

```bash
pytest
```

You can run specific test files or directories:

```bash
pytest tests/database/
pytest tests/web_app/test_leads_router.py
```

Add `-s` to see print statements and `--log-cli-level DEBUG` for detailed logging during tests.

## Project Structure

```
networking_assistant/
├── .env                  # Local environment variables (ignored by git)
├── .env.example          # Example environment variables
├── current_state.txt     # Temporary state file
├── leads.db              # Default SQLite database file (ignored by git)
├── requirements.txt      # Python dependencies
├── main.py               # Main application entry point (TBD)
├── src/                  # Source code
│   ├── api_integration/  # Clients for external APIs (Greenhouse, Lever, Notion)
│   ├── config/           # Configuration management
│   ├── core/             # Core logic (Orchestrator, Exceptions, Retry Utils)
│   ├── data_acquisition/ # Data scraping modules (LinkedIn, Company Info)
│   ├── data_processing/  # Data cleaning and processing (Lead Processor)
│   ├── database/         # Database interaction (Models, DB Manager, Utils)
│   ├── output_generation/# Modules for exporting data
│   └── web_app/          # FastAPI web application (API main, Routers, Schemas)
├── tests/                # Pytest tests mirroring src structure
├── scripts/              # Utility scripts (e.g., PRD files)
├── docs/                 # Project documentation
├── prd/                  # Product Requirement Documents
└── README.md             # This file
```

## Contributing

Contributions are welcome! Please follow standard Git workflow practices (fork, branch, pull request).

## License

(Specify License - e.g., MIT, Apache 2.0, or leave blank if private) 