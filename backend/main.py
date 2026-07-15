import os
import json
import logging
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Date, Time, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from dotenv import load_dotenv
# LangGraph and Groq imports
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END
from groq import Groq
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Default to SQLite inside backend folder for zero-setup execution
    DATABASE_URL = "sqlite:///./hcp_crm.db"
# Database setup
# check_same_thread=False is needed only for SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
# SQLAlchemy Models
class HCP(Base):
    __tablename__ = "hcps"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    specialty = Column(String(100), nullable=False)
    hospital = Column(String(200), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    interactions = relationship("Interaction", back_populates="hcp")
class Interaction(Base):
    __tablename__ = "interactions"
    id = Column(Integer, primary_key=True, index=True)
    hcp_id = Column(Integer, ForeignKey("hcps.id"), nullable=False)
    interaction_type = Column(String(50), nullable=False) # Meeting, Call, Email, Webcast
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    attendees = Column(Text, nullable=False) # JSON array of strings
    topics_discussed = Column(Text, nullable=False)
    materials_shared = Column(Text, nullable=False) # JSON array of strings
    sentiment = Column(String(50), default="Neutral") # Positive, Neutral, Negative
    created_at = Column(DateTime, default=datetime.utcnow)
    
    hcp = relationship("HCP", back_populates="interactions")
# Create tables
Base.metadata.create_all(bind=engine)
# Helper function to get DB Session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# Seed database if empty
def seed_database():
    db = SessionLocal()
    try:
        if db.query(HCP).count() == 0:
            logger.info("Seeding database with sample HCPs...")
            hcp1 = HCP(name="Dr. Sarah Jenkins", specialty="Cardiology", hospital="St. Jude Medical Center", email="sarah.jenkins@stjude.org")
            hcp2 = HCP(name="Dr. Robert Chen", specialty="Oncology", hospital="Metro Health Hospital", email="r.chen@metrohealth.org")
            hcp3 = HCP(name="Dr. Emily Taylor", specialty="Pediatrics", hospital="Children's Clinic", email="emily.taylor@childrens.org")
            hcp4 = HCP(name="Dr. James Wilson", specialty="Neurology", hospital="Brain & Spine Institute", email="j.wilson@bsi.org")
            db.add_all([hcp1, hcp2, hcp3, hcp4])
            db.commit()
            
            # Seed a default interaction
            db.refresh(hcp1)
            past_interaction = Interaction(
                hcp_id=hcp1.id,
                interaction_type="Meeting",
                date=date(2026, 7, 10),
                time=time(14, 30),
                attendees=json.dumps(["Dr. Sarah Jenkins", "Alex Rivera (Rep)"]),
                topics_discussed="Discussed Prodo-X safety profile, efficacy in hypertensive patients, and positive clinical trial readouts.",
                materials_shared=json.dumps(["Prodo-X Brochure", "Safety Reprint"]),
                sentiment="Positive"
            )
            db.add(past_interaction)
            db.commit()
            logger.info("Seeding complete.")
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()
seed_database()
# Pydantic Schemas
class HCPSchema(BaseModel):
    id: int
    name: str
    specialty: str
    hospital: str
    email: str
    class Config:
        from_attributes = True
class InteractionCreate(BaseModel):
    hcp_id: int
    interaction_type: str
    date: str # YYYY-MM-DD
    time: str # HH:MM
    attendees: List[str]
    topics_discussed: str
    materials_shared: List[str]
    sentiment: Optional[str] = "Neutral"
class InteractionUpdate(BaseModel):
    interaction_type: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    attendees: Optional[List[str]] = None
    topics_discussed: Optional[str] = None
    materials_shared: Optional[List[str]] = None
    sentiment: Optional[str] = None
class InteractionResponse(BaseModel):
    id: int
    hcp_id: int
    hcp_name: str
    interaction_type: str
    date: str
    time: str
    attendees: List[str]
    topics_discussed: str
    materials_shared: List[str]
    sentiment: str
    created_at: str
    class Config:
        from_attributes = True
class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = [] # list of {"role": "user/assistant", "content": "..."}
    current_form: Optional[Dict[str, Any]] = {} # current client form state
class ChatResponse(BaseModel):
    reply: str
    proposed_form: Dict[str, Any]
    proposed_compliance_report: Optional[Dict[str, Any]] = None
    tools_executed: List[str]

# Initialize FastAPI
app = FastAPI(title="AI-First CRM HCP Module Backend")
# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ----------------- DB Operations / Tool Internals -----------------
def db_search_hcp(db: Session, query: str) -> List[Dict[str, Any]]:
    results = db.query(HCP).filter(
        (HCP.name.ilike(f"%{query}%")) | 
        (HCP.specialty.ilike(f"%{query}%")) | 
        (HCP.hospital.ilike(f"%{query}%"))
    ).all()
    return [{"id": h.id, "name": h.name, "specialty": h.specialty, "hospital": h.hospital, "email": h.email} for h in results]
def db_log_interaction(db: Session, data: Dict[str, Any]) -> Dict[str, Any]:
    # Resolve HCP by name if id not provided
    hcp_id = data.get("hcp_id")
    hcp_name = data.get("hcp_name")
    
    if not hcp_id and hcp_name:
        # Search for HCP
        hcp = db.query(HCP).filter(HCP.name.ilike(f"%{hcp_name}%")).first()
        if not hcp:
            # Create a mock HCP on the fly if it doesn't exist
            # Generate a unique email by using a timestamp
            import time
            timestamp = int(time.time())
            clean_name = hcp_name.lower().replace(' ', '.').replace('dr.', '').replace('.', '')
            new_hcp = HCP(name=hcp_name, specialty="General Medicine", hospital="Community Hospital", email=f"{clean_name}{timestamp}@hospital.com")
            db.add(new_hcp)
            db.commit()
            db.refresh(new_hcp)
            hcp_id = new_hcp.id
        else:
            hcp_id = hcp.id
    if not hcp_id:
        raise ValueError("HCP name or ID must be provided to log an interaction.")
    # Parse date/time strings
    try:
        date_val = datetime.strptime(data["date"], "%Y-%m-%d").date()
    except Exception:
        date_val = date.today()
        
    try:
        time_val = datetime.strptime(data["time"], "%H:%M").time()
    except Exception:
        time_val = datetime.now().time()
    # Determine sentiment from topics_discussed if not explicitly set
    sentiment = data.get("sentiment")
    if not sentiment or sentiment == "Neutral":
        topics = data.get("topics_discussed", "").lower()
        if any(w in topics for w in ["positive", "agree", "excited", "interest", "good", "satisfied", "efficacy", "love"]):
            sentiment = "Positive"
        elif any(w in topics for w in ["unhappy", "concerned", "negative", "adverse", "risk", "warn", "difficult"]):
            sentiment = "Negative"
        else:
            sentiment = "Neutral"
    new_interaction = Interaction(
        hcp_id=hcp_id,
        interaction_type=data.get("interaction_type", "Meeting"),
        date=date_val,
        time=time_val,
        attendees=json.dumps(data.get("attendees", [])),
        topics_discussed=data.get("topics_discussed", ""),
        materials_shared=json.dumps(data.get("materials_shared", [])),
        sentiment=sentiment
    )
    db.add(new_interaction)
    db.commit()
    db.refresh(new_interaction)
    
    hcp = db.query(HCP).filter(HCP.id == hcp_id).first()
    return {
        "id": new_interaction.id,
        "hcp_id": hcp_id,
        "hcp_name": hcp.name if hcp else "Unknown",
        "interaction_type": new_interaction.interaction_type,
        "date": str(new_interaction.date),
        "time": new_interaction.time.strftime("%H:%M"),
        "attendees": json.loads(new_interaction.attendees),
        "topics_discussed": new_interaction.topics_discussed,
        "materials_shared": json.loads(new_interaction.materials_shared),
        "sentiment": new_interaction.sentiment,
        "created_at": str(new_interaction.created_at)
    }
def db_edit_interaction(db: Session, interaction_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    interaction = db.query(Interaction).filter(Interaction.id == interaction_id).first()
    if not interaction:
        raise ValueError(f"Interaction with ID {interaction_id} not found.")
    
    if "interaction_type" in updates:
        interaction.interaction_type = updates["interaction_type"]
    if "date" in updates:
        try:
            interaction.date = datetime.strptime(updates["date"], "%Y-%m-%d").date()
        except Exception:
            pass
    if "time" in updates:
        try:
            interaction.time = datetime.strptime(updates["time"], "%H:%M").time()
        except Exception:
            pass
    if "attendees" in updates:
        interaction.attendees = json.dumps(updates["attendees"])
    if "topics_discussed" in updates:
        interaction.topics_discussed = updates["topics_discussed"]
    if "materials_shared" in updates:
        interaction.materials_shared = json.dumps(updates["materials_shared"])
    if "sentiment" in updates:
        interaction.sentiment = updates["sentiment"]
        
    db.commit()
    db.refresh(interaction)
    hcp = db.query(HCP).filter(HCP.id == interaction.hcp_id).first()
    return {
        "id": interaction.id,
        "hcp_id": interaction.hcp_id,
        "hcp_name": hcp.name if hcp else "Unknown",
        "interaction_type": interaction.interaction_type,
        "date": str(interaction.date),
        "time": interaction.time.strftime("%H:%M"),
        "attendees": json.loads(interaction.attendees),
        "topics_discussed": interaction.topics_discussed,
        "materials_shared": json.loads(interaction.materials_shared),
        "sentiment": interaction.sentiment,
        "created_at": str(interaction.created_at)
    }
def db_get_interaction_history(db: Session, hcp_name: str) -> List[Dict[str, Any]]:
    hcp = db.query(HCP).filter(HCP.name.ilike(f"%{hcp_name}%")).first()
    if not hcp:
        return []
    
    interactions = db.query(Interaction).filter(Interaction.hcp_id == hcp.id).order_by(Interaction.date.desc()).limit(3).all()
    
    results = []
    for i in interactions:
        results.append({
            "id": i.id,
            "hcp_name": hcp.name,
            "interaction_type": i.interaction_type,
            "date": str(i.date),
            "time": i.time.strftime("%H:%M"),
            "attendees": json.loads(i.attendees),
            "topics_discussed": i.topics_discussed,
            "materials_shared": json.loads(i.materials_shared),
            "sentiment": i.sentiment,
        })
    return results
def local_check_compliance(topics_discussed: str, materials_shared: List[str]) -> Dict[str, Any]:
    warnings = []
    topics = topics_discussed.lower()
    materials = [m.lower() for m in materials_shared]
    
    # Example pharma compliance checks:
    # 1. Off-label discussion warning
    if "off-label" in topics or "unapproved" in topics or "experimental use" in topics:
        warnings.append("WARNING: Discussing off-label uses of approved drugs is highly regulated. Ensure all statements are aligned with scientific exchange policies.")
    
    # 2. Disease cure claim check
    if "cure cancer" in topics or "guarantees recovery" in topics or "100% cure" in topics:
        warnings.append("WARNING: Making absolute therapeutic outcome claims (e.g. 'curing cancer') is prohibited under FDA promotional regulations.")
    
    # 3. Draft or internal materials warning
    for m in materials:
        if "draft" in m or "internal" in m or "training" in m or "confidential" in m:
            warnings.append(f"WARNING: The material '{m}' appears to be labeled for internal/training use only. Sharing internal materials with HCPs violates PhRMA Code.")
            
    # 4. Product-specific claims checks (e.g. "Prodo-X" requires mentioning safety info)
    if "prodo-x" in topics:
        if "safety" not in topics and "adverse" not in topics and "side effect" not in topics:
            warnings.append("WARNING: Discussions regarding 'Prodo-X' efficacy must be balanced with its safety profile/adverse events information (Fair Balance Requirement).")
    status = "WARNING" if warnings else "PASS"
    return {
        "status": status,
        "warnings": warnings,
        "checked_at": datetime.now().isoformat()
    }
# ----------------- LangGraph Agent Setup -----------------
# Define State
class AgentState(TypedDict):
    messages: List[Dict[str, str]]
    form_data: Dict[str, Any]
    tools_executed: List[str]
    compliance_report: Optional[Dict[str, Any]]
    db_session: Any
# Define Tool schemas for Groq API
tools_definition = [
    {
        "type": "function",
        "function": {
            "name": "log_interaction",
            "description": "Log a brand new interaction with a healthcare professional (HCP) to the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hcp_name": {"type": "string", "description": "The exact name of the doctor / HCP, e.g. Dr. Sarah Jenkins"},
                    "interaction_type": {"type": "string", "enum": ["Meeting", "Call", "Email", "Webcast"], "description": "Type of interaction"},
                    "date": {"type": "string", "description": "Date of interaction (YYYY-MM-DD)"},
                    "time": {"type": "string", "description": "Time of interaction (HH:MM)"},
                    "attendees": {"type": "array", "items": {"type": "string"}, "description": "List of attendees present"},
                    "topics_discussed": {"type": "string", "description": "Full summaries or transcripts of what was discussed"},
                    "materials_shared": {"type": "array", "items": {"type": "string"}, "description": "List of materials or brochures shared"}
                },
                "required": ["hcp_name", "topics_discussed"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_interaction",
            "description": "Modify an existing interaction that was previously logged using its interaction_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "interaction_id": {"type": "integer", "description": "The unique ID of the interaction record to modify"},
                    "updates": {
                        "type": "object",
                        "properties": {
                            "interaction_type": {"type": "string", "enum": ["Meeting", "Call", "Email", "Webcast"]},
                            "date": {"type": "string"},
                            "time": {"type": "string"},
                            "attendees": {"type": "array", "items": {"type": "string"}},
                            "topics_discussed": {"type": "string"},
                            "materials_shared": {"type": "array", "items": {"type": "string"}},
                            "sentiment": {"type": "string"}
                        }
                    }
                },
                "required": ["interaction_id", "updates"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_hcp",
            "description": "Search the database for Healthcare Professionals (HCPs) by name, specialty, or hospital.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "HCP name, specialty, or hospital, e.g. sarah or cardiology"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_interaction_history",
            "description": "Fetch the recent history of interactions logged for a specific HCP by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hcp_name": {"type": "string", "description": "The name of the HCP"}
                },
                "required": ["hcp_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_compliance",
            "description": "Analyze topics discussed and materials shared for pharmaceutical promotional compliance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topics_discussed": {"type": "string", "description": "Text description of discussion topics"},
                    "materials_shared": {"type": "array", "items": {"type": "string"}, "description": "List of shared materials"}
                },
                "required": ["topics_discussed"]
            }
        }
    }
]
SYSTEM_PROMPT = """You are an intelligent, AI-first CRM assistant specialized for Life Sciences sales representatives.
Your task is to help reps log and manage their interactions with Healthcare Professionals (HCPs).
You have access to 5 tools:
1. log_interaction (logs a new interaction to the DB)
2. edit_interaction (modifies an existing logged interaction)
3. search_hcp (searches for doctors/HCPs by name, specialty, or hospital)
4. get_interaction_history (retrieves historical records for an HCP)
5. check_compliance (analyzes discussions/materials for compliance guidelines)
RULES OF BEHAVIOR:
1. If the user provides details about an interaction (e.g. "I met Dr. Sarah Jenkins today, discussed Prodo-X efficacy, shared a brochure"), call the `log_interaction` tool.
2. If the user wants to update a record (e.g. "change the date of interaction 5 to yesterday"), call `edit_interaction`.
3. If the user mentions a doctor but you are unsure of their details, use `search_hcp` first.
4. When you log or edit an interaction, also call the `check_compliance` tool to verify the discussion points are FDA/PhRMA compliant.
5. In addition to calling tools, you MUST return a helpful summary to the user explaining what you did, referencing any warnings or suggestions.
6. Make sure to sync the 'form_data' in the state with the details extracted so the frontend form updates in real time.
7. Once you have called log_interaction (or edit_interaction) successfully in this turn, do NOT call it again - simply summarize the result for the user in plain text.
Current date is 2026-07-14. Assume default time is 20:00 (8:00 PM) if not specified."""
# Fallback AI simulation (if Groq API key is missing or fails)
def run_simulated_ai(state: AgentState) -> Dict[str, Any]:
    last_message = state["messages"][-1]["content"]
    lower_msg = last_message.lower()
    db = state["db_session"]
    current_form = state.get("form_data", {})
    
    reply = ""
    tools_run = []
    import re
    
    # Words that should never be treated as an HCP's actual name
    NAME_STOPWORDS = {
        'dr', 'doctor', 'a', 'an', 'the', 'and', 'with', 'for', 'to', 'from',
        'today', 'yesterday', 'tomorrow', 'or', 'so', 'but', 'at', 'in', 'on',
        'i', 'attend', 'attended', 'call', 'meeting', 'according'
    }

    # Helper function to extract names from message
    def extract_name(text):
        # 1. Look for "Dr./Doctor <Name>" case-INSENSITIVELY (handles "dr bhargavi" as well
        #    as "Dr. Bhargavi"). Captures up to 2 following words, then strips any that
        #    are themselves filler/title words so "dr" never becomes the name itself.
        patterns = [
            # allow a stray "." either right after "dr" (dr.mallikarjun) or after the
            # space, which happens a lot with voice-transcription typos (dr .mallikarjun)
            r'dr\.?\s*\.?\s*([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
            r'doctor\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(' ,.!?;:"')
                tokens = [w for w in candidate.split() if w.lower() not in NAME_STOPWORDS]
                if tokens:
                    name = ' '.join(w.capitalize() for w in tokens[:2])
                    return f"Dr. {name}"
        # 2. Fall back to any capitalized word sequence (e.g. properly-cased "Sarah Jenkins")
        match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', text)
        if match:
            name = match.group(1)
            if name.lower() not in NAME_STOPWORDS:
                return f"Dr. {name}" if "Dr." not in text else match.group(0)
        return None
    
    MONTHS = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
        'aug': 8, 'august': 8, 'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12
    }
    MONTH_ALT = '|'.join(MONTHS.keys())

    # Helper function to extract date
    def extract_date(text):
        t = text.lower()

        # 1. ISO format YYYY-MM-DD
        m = re.search(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b', text)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).strftime("%Y-%m-%d")
            except ValueError:
                pass

        # 2. DD/MM/YYYY or DD-MM-YYYY
        m = re.search(r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b', text)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).strftime("%Y-%m-%d")
            except ValueError:
                pass

        # 3. "14 july 2025" / "14,july 2025" / "14th july 2025"
        m = re.search(rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s*({MONTH_ALT})\.?\s*,?\s*(\d{{4}})\b', t)
        if m:
            try:
                return date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))).strftime("%Y-%m-%d")
            except ValueError:
                pass

        # 4. "july 14 2025" / "july 14, 2025"
        m = re.search(rf'\b({MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b', t)
        if m:
            try:
                return date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2))).strftime("%Y-%m-%d")
            except ValueError:
                pass

        # 5. Relative dates
        today = date.today()
        if "today" in t:
            return today.strftime("%Y-%m-%d")
        if "yesterday" in t:
            return (today - timedelta(days=1)).strftime("%Y-%m-%d")
        if "tomorrow" in t:
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")

        return today.strftime("%Y-%m-%d")

    
    # Helper function to extract time
    def extract_time(text):
        # Look for HH:MM format
        time_match = re.search(r'\d{1,2}:\d{2}', text)
        if time_match:
            return time_match.group(0)
        return datetime.now().strftime("%H:%M")
    
    # 1. Search HCP check
    if "search" in lower_msg or "find doctor" in lower_msg or "find hcp" in lower_msg:
        # Extract query - remove common words and get the actual search term
        query = last_message
        for word in ["search", "find", "doctor", "hcp", "for", "a", "an", "the"]:
            query = re.sub(re.escape(word), "", query, flags=re.IGNORECASE)
        query = query.strip()
        hcps = db_search_hcp(db, query if query else "Sarah")
        reply = f"I searched the database for '{query if query else 'Sarah'}'. Here is what I found:\n" + "\n".join([f"- {h['name']} ({h['specialty']} at {h['hospital']})" for h in hcps])
        tools_run.append("search_hcp")
        
    # 2. Get interaction history check
    elif "history" in lower_msg or "past interactions" in lower_msg or "previous" in lower_msg:
        # Extract doctor name from message
        hcp_name = extract_name(last_message)
        if not hcp_name:
            # Fallback to form data if available
            hcp_name = current_form.get("hcp_name") if current_form else None
        if not hcp_name:
            hcp_name = "Dr. Sarah Jenkins"  # Final fallback
                
        history = db_get_interaction_history(db, hcp_name)
        tools_run.append("get_interaction_history")
        if history:
            reply = f"Here are the recent interactions for {hcp_name}:\n"
            for h in history:
                reply += f"- {h['date']}: {h['interaction_type']} - '{h['topics_discussed']}' (Sentiment: {h['sentiment']})\n"
        else:
            reply = f"No past interactions found for {hcp_name}."
            
    # 3. Edit interaction check
    elif "edit" in lower_msg or "update" in lower_msg or "change" in lower_msg:
        # Extract interaction ID
        interaction_id = None
        id_match = re.search(r'\b\d+\b', last_message)
        if id_match:
            interaction_id = int(id_match.group(0))
        elif current_form and "id" in current_form:
            interaction_id = current_form["id"]
        
        if not interaction_id:
            reply = "Please specify which interaction ID you want to edit."
        else:
            updates = {}
            
            # Extract interaction type
            if "call" in lower_msg:
                updates["interaction_type"] = "Call"
            elif "email" in lower_msg:
                updates["interaction_type"] = "Email"
            elif "webcast" in lower_msg:
                updates["interaction_type"] = "Webcast"
            elif "meeting" in lower_msg:
                updates["interaction_type"] = "Meeting"
            
            # Extract topics - use the actual message content after keywords
            if "topic" in lower_msg or "discuss" in lower_msg:
                # Try to extract what comes after discussion keywords
                for keyword in ["discussed", "topic", "about", "regarding"]:
                    if keyword in lower_msg:
                        idx = lower_msg.find(keyword)
                        topics = last_message[idx:].replace(keyword, "", 1).strip(" ,.")
                        if topics:
                            updates["topics_discussed"] = topics
                            break
                if "topics_discussed" not in updates:
                    updates["topics_discussed"] = last_message  # Use full message as fallback
            
            # Extract materials
            if "material" in lower_msg or "brochure" in lower_msg or "shared" in lower_msg:
                materials = []
                # Look for material names in the message
                if "brochure" in lower_msg:
                    materials.append("Brochure")
                if "slide" in lower_msg:
                    materials.append("Slide Deck")
                if "reprint" in lower_msg:
                    materials.append("Reprint")
                # Try to extract quoted material names
                quoted = re.findall(r'"([^"]+)"', last_message)
                materials.extend(quoted)
                if materials:
                    updates["materials_shared"] = materials
            
            # Extract date
            if "date" in lower_msg:
                updates["date"] = extract_date(last_message)
            
            # Extract time
            if "time" in lower_msg:
                updates["time"] = extract_time(last_message)
            
            # Extract sentiment
            if "positive" in lower_msg:
                updates["sentiment"] = "Positive"
            elif "negative" in lower_msg:
                updates["sentiment"] = "Negative"
            elif "neutral" in lower_msg:
                updates["sentiment"] = "Neutral"
            
            try:
                updated = db_edit_interaction(db, interaction_id, updates)
                reply = f"Successfully updated interaction ID {interaction_id} for {updated['hcp_name']}. The form and database have been updated."
                tools_run.append("edit_interaction")
                state["form_data"].update(updated)
            except Exception as e:
                reply = f"Could not update interaction: {str(e)}"
            
    # 4. Log interaction (Default fallback if contains interaction-related keywords)
    elif any(d in lower_msg for d in ["dr.", "doctor", "met", "call", "email", "meeting", "log", "interaction", "discussed", "spoke", "today", "yesterday"]):
        # Extract HCP name from message - EXTRACTED VALUE TAKES PRIORITY
        hcp_name = extract_name(last_message)

        # Safety net: reject a "name" that's actually just filler/stopwords glued to
        # "Dr." (e.g. "Dr. And"). This is how garbage HCP records got created and then
        # persisted in the DB in the past, which then kept polluting future matches.
        if hcp_name:
            name_tokens = [t.lower().strip('.') for t in hcp_name.replace("Dr.", "").split()]
            if not any(t and t not in NAME_STOPWORDS and len(t) > 2 for t in name_tokens):
                hcp_name = None

        # Extra heuristic: if message contains the HCP name (case-insensitive) but without "Dr.", match it from DB.
        if not hcp_name:
            db_hcps = db.query(HCP).all()
            lowered = last_message.lower()
            for h in db_hcps:
                # match full name or last name token
                if h.name.lower() in lowered:
                    hcp_name = h.name
                    break
                last_token = h.name.split()[-1].lower() if h.name else ''
                # Guard against matching on a common/filler word (e.g. a garbage HCP
                # record whose "name" ended up being "...and"). A real surname is a
                # standalone word boundary match, not just any substring, and must not
                # itself be a stopword.
                if (last_token and len(last_token) > 2 and last_token not in NAME_STOPWORDS
                        and re.search(rf'\b{re.escape(last_token)}\b', lowered)):
                    hcp_name = h.name
                    break

        # No confident name found via patterns or DB match. We deliberately do NOT try to
        # guess a name from a random nearby word (e.g. "attendees", "tomorrow") - that was
        # producing garbage HCP records. Only fall back to the form's current HCP if it's a
        # REAL selected record (has an hcp_id), not just leftover typed text.
        if not hcp_name and current_form and current_form.get("hcp_id"):
            hcp_name = current_form.get("hcp_name")

        if not hcp_name:
            # We genuinely don't know who this interaction is with. Rather than guessing
            # (which previously produced garbage like "Dr. Attendies" or reused stale
            # text from the form), extract what else we can and ask the user to clarify.
            interaction_type = "Meeting"
            if "call" in lower_msg:
                interaction_type = "Call"
            elif "email" in lower_msg:
                interaction_type = "Email"
            elif "webcast" in lower_msg:
                interaction_type = "Webcast"

            sentiment = "Neutral"
            if "positive" in lower_msg:
                sentiment = "Positive"
            elif "negative" in lower_msg:
                sentiment = "Negative"

            count_match = re.search(r'\b(\d{1,3})\b\s*(attend\w*|people|participants)', lower_msg)
            attendee_count = int(count_match.group(1)) if count_match else None
            attendees = [f"{attendee_count} Attendees"] if attendee_count else []

            date_val = extract_date(last_message)
            topics = last_message.strip(" ,.")

            comp = local_check_compliance(topics, [])
            state["compliance_report"] = comp
            tools_run.append("check_compliance")

            # Offer this as a preview only - do NOT write to the database without a known HCP.
            state["form_data"] = {
                "interaction_type": interaction_type,
                "date": date_val,
                "attendees": attendees,
                "topics_discussed": topics,
                "sentiment": sentiment
            }
            reply = (
                "I've captured the details of this interaction, but I couldn't tell which HCP it's with - "
                "no doctor's name was mentioned, and there isn't one currently selected on the form. "
                "Could you tell me who this interaction was with (e.g. 'with Dr. Bhargavi')? "
                "I've filled in the other fields I could detect (type, date, attendee count, sentiment) as a preview."
            )
        else:
            # If we produced a name, ensure it exists in DB before logging.
            # (Otherwise db_log_interaction will create a mock HCP, but with the correct name.)
            # This keeps subsequent resolutions consistent.
            existing = db.query(HCP).filter(HCP.name.ilike(f"%{hcp_name}%")).first()
            if not existing:
                # Create a mock HCP with that exact name
                import time
                timestamp = int(time.time())
                clean_name = hcp_name.lower().replace(' ', '.').replace('dr.', '').replace('.', '')
                new_hcp = HCP(
                    name=hcp_name,
                    specialty="General Medicine",
                    hospital="Community Hospital",
                    email=f"{clean_name}{timestamp}@hospital.com",
                )
                db.add(new_hcp)
                db.commit()
                db.refresh(new_hcp)


            
            # Extract interaction type - EXTRACTED VALUE TAKES PRIORITY
            interaction_type = "Meeting"
            if "call" in lower_msg:
                interaction_type = "Call"
            elif "email" in lower_msg:
                interaction_type = "Email"
            elif "webcast" in lower_msg:
                interaction_type = "Webcast"
            # Only use form value if no type was extracted from message
            elif not any(t in lower_msg for t in ["call", "email", "webcast", "meeting"]) and current_form and "interaction_type" in current_form:
                interaction_type = current_form["interaction_type"]
            
            # Extract sentiment explicitly mentioned - EXTRACTED VALUE TAKES PRIORITY
            sentiment = "Neutral"
            if "positive" in lower_msg:
                sentiment = "Positive"
            elif "negative" in lower_msg:
                sentiment = "Negative"
            elif "neutral" in lower_msg:
                sentiment = "Neutral"
            # Only use form value if no sentiment was extracted from message
            elif not any(s in lower_msg for s in ["positive", "negative", "neutral"]) and current_form and "sentiment" in current_form:
                sentiment = current_form["sentiment"]
            
            # Extract attendees - EXTRACTED VALUE TAKES PRIORITY
            attendees = [hcp_name]
            # If user mentions an attendee count (e.g. "22 attendees"), create placeholders if we don't extract names.
            count_match = re.search(r'\b(\d{1,3})\b\s*(attend\w*|people|participants)', lower_msg)
            attendee_count = int(count_match.group(1)) if count_match else None

            # Add any other capitalized names found (excluding common words).
            # Use a regex instead of a naive split() so names are still detected when
            # glued to stray punctuation (e.g. "dr .Rajyam" -> "Rajyam").
            common_words = {'and', 'the', 'with', 'for', 'but', 'or', 'so', 'at', 'in', 'on', 'to', 'from', 'today', 'tomorrow', 'yesterday'}
            extracted_names = []
            for word in re.findall(r"[A-Z][a-zA-Z]+", last_message):
                if len(word) > 2 and word not in hcp_name and word.lower() not in common_words:
                    extracted_names.append(word)

            if extracted_names:
                attendees.extend(extracted_names)
            # Only use form attendees if no names were extracted from message AND the form
            # actually has attendees to offer - an empty [] on the form should never wipe
            # out the hcp_name we already put in `attendees`.
            elif current_form and current_form.get("attendees"):
                attendees = current_form["attendees"]

            # If user mentions an attendee count (e.g. "22 attendees") but no specific names,
            # show it as a single "N Attendees" summary tag rather than N separate placeholder tags.
            if attendee_count is not None and not extracted_names and attendees == [hcp_name]:
                attendees = [hcp_name, f"{attendee_count} Attendees"]
            elif attendee_count is not None and extracted_names and attendee_count > len(attendees):
                # We have some real names; note how many additional unnamed attendees there were.
                remaining = attendee_count - len(attendees)
                attendees.append(f"+{remaining} more attendees")


            
            # Extract materials shared - EXTRACTED VALUE TAKES PRIORITY
            materials = []
            # "brochure" is commonly misspelled by reps/voice-transcription (e.g. "brouchers",
            # "broucher"). Match loosely on the bro...ch... shape instead of exact strings.
            if re.search(r'\bbro\w*ch\w*\b', lower_msg):
                materials.append("Brochure")
            if "slide" in lower_msg or "deck" in lower_msg:
                materials.append("Slide Deck")
            if "reprint" in lower_msg:
                materials.append("Reprint")
            if "sample" in lower_msg or "vial" in lower_msg:
                materials.append("Sample Pack")
            if "monograph" in lower_msg:
                materials.append("Product Monograph")
            # Extract quoted materials
            quoted_materials = re.findall(r'"([^"]+)"', last_message)
            materials.extend(quoted_materials)
            # Only use form materials if none were extracted AND the form actually has some -
            # an empty [] on the form should never wipe out materials we just extracted.
            if not materials and current_form and current_form.get("materials_shared"):
                materials = current_form["materials_shared"]
            
            # Extract topics discussed - EXTRACTED VALUE TAKES PRIORITY
            topics = last_message
            # Remove common phrases to get the core topic
            for phrase in ["met with", "spoke to", "called", "emailed", "discussed", "about", "regarding", "the sentiment was", "sentiment was", "i sent", "sent the"]:
                topics = re.sub(re.escape(phrase), "", topics, flags=re.IGNORECASE)
            topics = topics.strip(" ,.")
            if not topics or len(topics) < 3:
                topics = last_message  # Use full message if extraction fails
            # Only use form topics if extraction resulted in very short/empty topics
            if len(topics) < 5 and current_form and "topics_discussed" in current_form:
                topics = current_form["topics_discussed"]
            
            # Extract date and time - EXTRACTED VALUE TAKES PRIORITY
            date_val = extract_date(last_message)
            time_val = extract_time(last_message)
            
            # Only use form date/time if no date was actually mentioned in the message
            date_was_mentioned = (
                re.search(r'\d{4}-\d{2}-\d{2}', last_message) or
                re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', last_message) or
                re.search(rf'\b({MONTH_ALT})\b', lower_msg) or
                "today" in lower_msg or "yesterday" in lower_msg or "tomorrow" in lower_msg
            )
            if not date_was_mentioned:
                if current_form and "date" in current_form:
                    date_val = current_form["date"]
            if not re.search(r'\d{1,2}:\d{2}', last_message):
                if current_form and "time" in current_form:
                    time_val = current_form["time"]
            
            # Perform compliance check
            comp = local_check_compliance(topics, materials if isinstance(materials, list) else [])
            state["compliance_report"] = comp
            tools_run.append("check_compliance")
            
            # Save to DB
            log_data = {
                "hcp_name": hcp_name,
                "interaction_type": interaction_type,
                "date": date_val,
                "time": time_val,
                "attendees": attendees if isinstance(attendees, list) else [attendees],
                "topics_discussed": topics,
                "materials_shared": materials if isinstance(materials, list) else [],
                "sentiment": sentiment
            }
            
            try:
                logged = db_log_interaction(db, log_data)
                reply = f"I've logged a new {interaction_type} interaction with {hcp_name} on {date_val} at {time_val}. "
                reply += f"Topics: {topics[:100]}... "
                reply += f"Sentiment: {sentiment}. "
                if comp["status"] == "WARNING":
                    reply += "\n\n⚠️ **Compliance Warning**: " + "\n".join(comp["warnings"])
                else:
                    reply += "Compliance status: PASS ✅"
                tools_run.append("log_interaction")
                
                # Sync with state
                state["form_data"] = logged
            except Exception as e:
                reply = f"Error logging interaction: {str(e)}"
    else:
        reply = "I'm the CRM AI Assistant. You can describe an interaction (e.g. 'Met Dr. Sarah Jenkins, discussed Prodo-X efficacy, shared brochure') and I will automatically fill out the form and log it for you. You can also ask me to check history or edit existing entries."
    state["messages"].append({"role": "assistant", "content": reply})
    state["tools_executed"].extend(tools_run)
    return state
# Actual Groq Agent Node
def agent_node(state: AgentState) -> Dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not found. Running simulated AI agent.")
        return run_simulated_ai(state)
    try:
        client = Groq(api_key=api_key)
        # Format messages for API. A plain {"role","content"} copy loses the
        # tool_calls / tool_call_id fields that Groq's OpenAI-compatible API requires
        # once a tool has been executed - reconstruct them properly here.
        api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for msg in state["messages"]:
            if msg["role"] == "assistant" and msg.get("tool_calls"):
                api_messages.append({
                    "role": "assistant",
                    "content": msg.get("content") or None,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"])
                            }
                        }
                        for tc in msg["tool_calls"]
                    ]
                })
            elif msg["role"] == "tool":
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.get("tool_call_id"),
                    "name": msg.get("name"),
                    "content": msg["content"]
                })
            else:
                api_messages.append({"role": msg["role"], "content": msg["content"]})
        logger.info("Calling Groq API (llama-3.1-8b-instant)...")
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=api_messages,
            tools=tools_definition,
            tool_choice="auto",
            temperature=0.2
        )
        
        assistant_msg = completion.choices[0].message
        
        # Check if the LLM requested any tool calls
        if assistant_msg.tool_calls:
            logger.info(f"Groq requested {len(assistant_msg.tool_calls)} tool calls.")
            # Convert tool calls to a JSON-compatible format for our state
            tool_calls = []
            for tc in assistant_msg.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
            
            # Store tool calls in the message history so they can be processed by the tools node
            state["messages"].append({
                "role": "assistant", 
                "content": assistant_msg.content or "", 
                "tool_calls": tool_calls
            })
        else:
            state["messages"].append({
                "role": "assistant", 
                "content": assistant_msg.content or ""
            })
            
    except Exception as e:
        logger.error(f"Error calling Groq API: {e}. Falling back to simulation.")
        return run_simulated_ai(state)
        
    return state
# Actual Tools Node
def tools_node(state: AgentState) -> Dict[str, Any]:
    db = state["db_session"]
    last_msg = state["messages"][-1]
    
    if "tool_calls" not in last_msg:
        return state
        
    for tc in last_msg["tool_calls"]:
        tool_name = tc["name"]
        args = tc["arguments"]

        # Guard: never let a write-tool (log_interaction / edit_interaction) fire more
        # than once in the same turn. The LLM occasionally re-invokes it on the follow-up
        # turn using the previous tool result as input, which corrupts the record with a
        # JSON blob stuffed into topics_discussed. If we've already logged/edited this
        # turn, short-circuit with the cached result instead of touching the DB again.
        if tool_name in ("log_interaction", "edit_interaction") and tool_name in state["tools_executed"]:
            logger.warning(f"Blocked duplicate {tool_name} call in the same turn - reusing prior result.")
            state["messages"].append({
                "role": "tool",
                "name": tool_name,
                "tool_call_id": tc["id"],
                "content": json.dumps(state.get("form_data") or {"status": "already_completed"})
            })
            continue

        logger.info(f"Executing tool {tool_name} with arguments {args}")
        state["tools_executed"].append(tool_name)
        
        result = None
        try:
            if tool_name == "log_interaction":
                result = db_log_interaction(db, args)
                # Automatically run compliance check as well
                comp = local_check_compliance(args.get("topics_discussed", ""), args.get("materials_shared", []))
                state["compliance_report"] = comp
                state["form_data"] = result
                
            elif tool_name == "edit_interaction":
                result = db_edit_interaction(db, args["interaction_id"], args["updates"])
                state["form_data"] = result
                
            elif tool_name == "search_hcp":
                result = db_search_hcp(db, args["query"])
                
            elif tool_name == "get_interaction_history":
                result = db_get_interaction_history(db, args["hcp_name"])
                
            elif tool_name == "check_compliance":
                result = local_check_compliance(args["topics_discussed"], args.get("materials_shared", []))
                state["compliance_report"] = result
                
            # Append tool execution message
            state["messages"].append({
                "role": "tool",
                "name": tool_name,
                "tool_call_id": tc["id"],
                "content": json.dumps(result)
            })
            
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            state["messages"].append({
                "role": "tool",
                "name": tool_name,
                "tool_call_id": tc["id"],
                "content": json.dumps({"error": str(e)})
            })
            
    return state
# Routing logic
def should_continue(state: AgentState):
    last_message = state["messages"][-1]
    if "tool_calls" in last_message and last_message["tool_calls"]:
        return "tools"
    return "end"
# Compile LangGraph Workflow
workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tools_node)
workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", should_continue, {
    "tools": "tools",
    "end": END
})
workflow.add_edge("tools", "agent")
langgraph_app = workflow.compile()
# ----------------- FastAPI Routes -----------------
@app.get("/api/hcps", response_model=List[HCPSchema])
def get_hcps(db: Session = Depends(get_db)):
    return db.query(HCP).all()
@app.get("/api/hcps/search")
def search_hcps(query: str = Query(...), db: Session = Depends(get_db)):
    return db_search_hcp(db, query)
@app.get("/api/interactions")
def get_interactions(db: Session = Depends(get_db)):
    interactions = db.query(Interaction).order_by(Interaction.date.desc(), Interaction.id.desc()).all()
    results = []
    for i in interactions:
        hcp = db.query(HCP).filter(HCP.id == i.hcp_id).first()
        results.append({
            "id": i.id,
            "hcp_id": i.hcp_id,
            "hcp_name": hcp.name if hcp else "Unknown",
            "interaction_type": i.interaction_type,
            "date": str(i.date),
            "time": i.time.strftime("%H:%M"),
            "attendees": json.loads(i.attendees),
            "topics_discussed": i.topics_discussed,
            "materials_shared": json.loads(i.materials_shared),
            "sentiment": i.sentiment,
            "created_at": str(i.created_at)
        })
    return results
@app.post("/api/interactions")
def create_interaction(data: InteractionCreate, db: Session = Depends(get_db)):
    try:
        logged = db_log_interaction(db, data.dict())
        return logged
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
@app.put("/api/interactions/{id}")
def update_interaction(id: int, updates: InteractionUpdate, db: Session = Depends(get_db)):
    try:
        updated = db_edit_interaction(db, id, updates.dict(exclude_unset=True))
        return updated
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
@app.post("/api/chat", response_model=ChatResponse)
def chat_agent(request: ChatRequest, db: Session = Depends(get_db)):
    # Build LangGraph input state
    messages = []
    for msg in request.history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    # Add latest user message
    messages.append({"role": "user", "content": request.message})
    
    initial_state = {
        "messages": messages,
        "form_data": request.current_form,
        "tools_executed": [],
        "compliance_report": None,
        "db_session": db
    }
    
    try:
        # Execute LangGraph
        result_state = langgraph_app.invoke(initial_state)
        
        # Get final response from agent
        reply = ""
        # Search backward for the last assistant response that contains content
        for msg in reversed(result_state["messages"]):
            if msg["role"] == "assistant" and msg.get("content"):
                reply = msg["content"]
                break
                
        if not reply:
            reply = "I have successfully processed your request."
        
        # Ensure proposed_form is JSON-serializable (convert datetime objects to strings)
        proposed_form = result_state.get("form_data") or {}
        if proposed_form:
            proposed_form = dict(proposed_form)
            for key, value in list(proposed_form.items()):
                if hasattr(value, 'isoformat'):
                    proposed_form[key] = value.isoformat() if callable(getattr(value, 'isoformat', None)) else str(value)
                elif isinstance(value, list):
                    proposed_form[key] = [str(v) if hasattr(v, 'isoformat') else v for v in value]

        # Ensure proposed_compliance_report is JSON-serializable
        proposed_compliance_report = result_state.get("compliance_report")
        if proposed_compliance_report:
            proposed_compliance_report = dict(proposed_compliance_report) if not isinstance(proposed_compliance_report, dict) else proposed_compliance_report
            for key, value in list(proposed_compliance_report.items()):
                if hasattr(value, 'isoformat'):
                    proposed_compliance_report[key] = str(value)

        tools_executed = result_state.get("tools_executed") or []
        tools_executed = [str(t) for t in tools_executed]

        logger.info(f"Returning response - proposed keys: {list(proposed_form.keys()) if proposed_form else 'none'}, tools: {tools_executed}")

        return ChatResponse(
            reply=reply,
            proposed_form=proposed_form or {},
            proposed_compliance_report=proposed_compliance_report,
            tools_executed=tools_executed
        )
    except Exception as e:
        logger.error(f"Error in LangGraph: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI Agent execution failed: {repr(e)}")


@app.post("/api/compliance")
def check_compliance_route(data: Dict[str, Any]):
    topics = data.get("topics_discussed", "")
    materials = data.get("materials_shared", [])
    return local_check_compliance(topics, materials)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)