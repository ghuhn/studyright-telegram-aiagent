# AI Study Agent - Comprehensive Project Documentation

## 1. Project Overview

The **AI Study Agent** is a fully autonomous, cloud-hosted Telegram bot designed to serve as a 24/7 personal study assistant. Its primary function is to ingest educational materials (PDFs, Word documents, text files) seamlessly through direct Telegram uploads or by monitoring a dedicated Gmail inbox. 

Once received, the bot processes the documents, generates concise summaries, and maps the textual data into a mathematical vector database. This allows the user to query the bot at any time using natural language to retrieve highly specific answers derived directly from their personal study materials, effectively creating a "second brain" for studying. The architecture also includes context-isolation via "Subjects" ensuring that biology questions don't accidentally pull answers from history essays.

## 2. Core Features & Capabilities

*   **Multi-Channel Ingestion:** Users can upload documents directly by sending them to the Telegram bot, or by forwarding emails (with attachments) to a designated Gmail address.
*   **Intelligent Summarization:** Every ingested document is immediately parsed and summarized, providing the user with a quick overview of the material.
*   **Semantic Search (RAG):** The bot utilizes Retrieval-Augmented Generation. Users can ask complex questions (`/ask`), and the bot will search through the exact text of their uploaded documents to formulate an accurate answer.
*   **Subject Context Isolation:** (`/subject`) Users can switch between different study subjects (e.g., "Math", "Physics"). Documents uploaded and questions asked are strictly isolated to the currently active subject.
*   **Automated Flashcards:** (`/flashcards`) The bot can automatically generate study flashcards based on the documents stored within the active subject.
*   **Spaced Repetition Quizzes:** (`/quiz`) The bot can pull random chunks of text from the user's database and generate a pop-quiz question to test their knowledge.
*   **Notification Tracking:** (`/notification_history`) The bot maintains a persistent history of all background events, such as when it successfully processed an email in the background.

## 3. High-Level Architecture Flow

1.  **Ingestion:** A file arrives via a Telegram message or the background Gmail worker (`app/email_parser.py`).
2.  **Extraction:** The file is temporarily downloaded and processed by `app/document_parser.py` (using `fitz` for PDFs, `docx` for Word documents).
3.  **Summarization:** The raw text is sent to the LLM (Groq) via `app/llm.py` to generate a summary.
4.  **Vectorization:** The raw text is chopped into smaller chunks. `app/vector_db.py` uses `FastEmbed` to convert these text chunks into 384-dimensional mathematical arrays (embeddings).
5.  **Storage:** 
    *   The embeddings and original text chunks are uploaded to the Pinecone Vector Database.
    *   The document metadata (filename, subject) and the summary are saved to the Neon PostgreSQL relational database (`app/database.py`).
6.  **Retrieval:** When a user asks a question, the query is vectorized, matched against Pinecone to find the most relevant text chunks, and sent to the LLM to generate a final answer.

## 4. Technology Stack & Tools Used

Below is a comprehensive index of every tool, service, and major Python library utilized to bring the AI Study Agent to life, along with its specific usage in the project:

### Cloud Infrastructure & External Services

| Tool / Service | Category | Specific Usage in Project |
| :--- | :--- | :--- |
| **Telegram API** | User Interface | Acts as the entire frontend for the application. Users interact with the AI via a Telegram Bot. |
| **Render** | Cloud Hosting | Hosting provider running the Python backend server 24/7 on a Free Tier Web Service instance. |
| **Neon** | Relational Database | Serverless PostgreSQL cloud database. Stores User profiles, active subject contexts, document metadata, and background notification history logs. |
| **Pinecone** | Vector Database | Serverless vector database. Stores the mathematical embeddings of the study materials, allowing for incredibly fast semantic similarity searches during RAG operations. |
| **Groq** | LLM Provider | Provides the exceptionally fast open-source Large Language Models (specifically `llama-3.3-70b-versatile`) used for generating summaries, answering questions, and creating flashcards/quizzes. |
| **Google Cloud / Gmail API** | Email Provider | Provides OAuth2 authenticated API access allowing the background worker to continuously poll the designated Gmail inbox, bypass Render's outbound IMAP firewalls, and intercept emailed study materials. |

### Core Python Frameworks & Libraries

| Library | Category | Specific Usage in Project |
| :--- | :--- | :--- |
| **FastAPI** | Web Framework | The core ASGI web framework that receives incoming webhook HTTP requests from Telegram and orchestrates the backend logic. |
| **Uvicorn** | ASGI Server | The blazing fast web server that runs the FastAPI application and manages the asynchronous event loop on Render. |
| **python-telegram-bot** | Bot Framework | Translates the raw Telegram API payloads into manageable Python objects and asynchronous handler commands. |
| **SQLAlchemy** | Database ORM | Provides the Object Relational Mapping layer to interact safely with the Neon PostgreSQL database using Python classes. |
| **psycopg2-binary** | Database Driver | The low-level database driver required by SQLAlchemy to physically communicate with PostgreSQL servers. |

### Document Parsing & AI Libraries

| Library | Category | Specific Usage in Project |
| :--- | :--- | :--- |
| **PyMuPDF (`fitz`)** | Extraction | High-performance C++ backed library used to extract raw text content out of `.pdf` files. |
| **python-docx** | Extraction | Used to extract raw text content out of Microsoft Word `.docx` documents. |
| **FastEmbed** | AI Embedding | A lightweight, ONNX-backed library used to run the `all-MiniLM-L6-v2` neural network. Converts text chunks into 384-dimensional mathematical vectors efficiently within Render's 512MB RAM constraint, avoiding PyTorch OOM crashes. |
| **groq-python** | LLM Client | Official Python client library to interact with the Groq inference endpoints. |
| **pinecone** | Vector DB Client | Official Python client library to upsert vectors and query the Pinecone index. |

### Authentication & Utility Libraries

| Library | Category | Specific Usage in Project |
| :--- | :--- | :--- |
| **google-api-python-client** | Google Auth | Provides the `googleapiclient.discovery.build` interface to interact directly with the Gmail API endpoints. |
| **google-auth-oauthlib** | Google Auth | Handled the initial local OAuth2 consent flow to generate the `token.json` refresh tokens. |
| **google-auth-httplib2** | Google Auth | Provides transport mechanisms for the Google Auth libraries. |
| **pydantic & pydantic-settings** | Configuration | Safely manages and validates the application configuration and environment variables (`.env`). |
| **python-dotenv** | Configuration | Loads the local `.env` file into the system environment for local testing. |
| **asyncio** | Concurrency | Standard Python library used extensively (`await asyncio.to_thread()`) to prevent heavy synchronous functions (like FastEmbed mathematical array generation) from blocking the main Uvicorn web server event loop and triggering Render health-check timeouts. |
