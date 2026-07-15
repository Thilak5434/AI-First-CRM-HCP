
# AI-First Life Science CRM - HCP Module (Log Interaction Screen)

An AI-first Customer Relationship Management (CRM) system specifically designed for Life Sciences sales representatives. The module provides a dual-pane interface: a structured form on the left and a conversational AI assistant on the right.
Reps can log meetings, calls, and email interactions either manually through the form, via voice note transcription, or conversationally via the chat.

## Features

1. **Dual-Pane Interface**:
   - **Structured Form (Left)**: Log details like HCP name, interaction type, date/time, attendees, topics, materials shared, and sentiment. Syncs in real time with AI modifications.
   - **AI CRM Assistant (Right)**: Conversational interface using a **LangGraph** workflow running on **Groq (gemma2-9b-it)**.
2. **5 Specialized Agent Tools**:
   - `log_interaction`: Auto-summarizes, extracts entities, and creates database records.
   - `edit_interaction`: Modifies existing logged records via natural language updates.
   - `search_hcp`: Matches partial inputs to find matching doctors by name/specialty/hospital.
   - `get_interaction_history`: Queries recent history to help sales reps prepare.
   - `check_compliance`: Automatically audits discussion details against FDA and PhRMA guidelines (e.g. warning on off-label claims or unauthorized promotional materials).
3. **Voice Note Transcription**: Toggle consent to simulate talking to a mic. Speech is transcribed and processed to fill form fields and perform real-time compliance checks.
4. **Real-time Compliance Warnings**: Alerts reps to regulations (e.g., Fair Balance requirements when discussing products like *Prodo-X* without safety contexts).
5. **Interactive Review/Edit**: Click on any past interaction card to load it directly back into the editor for viewing or modification.

---

## Tech Stack

- **Frontend**: React (Vite), Redux Toolkit (State Management), Lucide Icons, Vanilla CSS (Glassmorphism layout, glowing highlights, responsive grid).
- **Backend**: Python 3.13, FastAPI, SQLAlchemy ORM.
- **Database**: SQLite (default, self-contained `hcp_crm.db`), compatible with MySQL/PostgreSQL via the `DATABASE_URL` environment variable.
- **AI Agent**: LangGraph state machine workflow with Groq LLM API.

---

## Getting Started

### 1. Prerequisites

- Python 3.10+
- Node.js v18+

### 2. Backend Setup

1. Open a terminal and navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate
   # On Linux/macOS:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the `backend` folder (you can copy `.env.example` or copy the contents below):
   ```env
   GROQ_API_KEY="your-groq-api-key-here"
   DATABASE_URL="sqlite:///./hcp_crm.db" # Default SQLite DB
   ```

   *Note: If `GROQ_API_KEY` is omitted, the backend runs a smart local fallback simulator to parse, extract, and execute LangGraph tools so that you can evaluate and demo the entire application without any setup or external API limits.*
5. Run the FastAPI development server:
   ```bash
   python main.py
   ```

   The backend will be available at `http://localhost:8000`. Database tables will be automatically created and pre-seeded with sample HCPs and interactions.

### 3. Frontend Setup

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install npm dependencies:
   ```bash
   npm install
   ```
3. Run the frontend development server:
   ```bash
   npm run dev
   ```
4. Open your browser and navigate to `http://localhost:5173`.

---

## Project Structure

```text
crm-hcp-project/
├── backend/
│   ├── main.py              # FastAPI Server, SQLAlchemy models, LangGraph Agent & Tools
│   ├── requirements.txt     # Python backend dependencies
│   ├── .env                 # API configuration keys
│   └── hcp_crm.db           # Local SQLite database (auto-generated)
├── frontend/
│   ├── src/
│   │   ├── main.jsx         # React bootstrap
│   │   ├── store.js         # Redux Toolkit store (actions, reducers, slices)
│   │   ├── App.jsx          # UI Layout & split-screen interface
│   │   └── index.css        # Vanilla CSS styles (Glassmorphic panels, styles)
│   ├── package.json         # Node packages
│   ├── index.html           # HTML template (Inter Google font link)
│   └── vite.config.js       # Vite server proxy configurations
└── README.md                # Project documentation
```

---

## Submission Details

- **Google Form Submission URL**: [https://forms.gle/XdvLNBJkbdVDGADM8](https://forms.gle/XdvLNBJkbdVDGADM8)
