"""
One-time migration script: copies all data from the local SQLite hcp_crm.db
into a PostgreSQL database.

Usage:
    1. Make sure PostgreSQL is running and you've created an empty database, e.g.:
         createdb hcp_crm
    2. Set DATABASE_URL in your .env to your Postgres connection string
       (e.g. postgresql://postgres:your_password@localhost:5432/hcp_crm)
    3. Run this script from the backend folder (where hcp_crm.db lives):
         python migrate_to_postgres.py

This only needs to be run once. After this, main.py will read DATABASE_URL
from .env and use PostgreSQL going forward - the old hcp_crm.db (SQLite file)
is left untouched as a backup.
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Date, Time, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

load_dotenv()

SQLITE_URL = "sqlite:///./hcp_crm.db"
POSTGRES_URL = os.getenv("DATABASE_URL")

if not POSTGRES_URL or not POSTGRES_URL.startswith("postgresql"):
    print("ERROR: Set DATABASE_URL in your .env to a postgresql:// connection string first.")
    sys.exit(1)

Base = declarative_base()

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
    interaction_type = Column(String(50), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    attendees = Column(Text, nullable=False)
    topics_discussed = Column(Text, nullable=False)
    materials_shared = Column(Text, nullable=False)
    sentiment = Column(String(50), default="Neutral")
    created_at = Column(DateTime)
    hcp = relationship("HCP", back_populates="interactions")


def main():
    sqlite_engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    postgres_engine = create_engine(POSTGRES_URL)

    SqliteSession = sessionmaker(bind=sqlite_engine)
    PostgresSession = sessionmaker(bind=postgres_engine)

    # Create tables on Postgres (safe to run even if they already exist)
    Base.metadata.create_all(bind=postgres_engine)

    sqlite_db = SqliteSession()
    pg_db = PostgresSession()

    try:
        if pg_db.query(HCP).count() > 0:
            print("PostgreSQL database already has data. Aborting to avoid duplicates.")
            print("If you want to re-run this, empty the hcps/interactions tables first.")
            return

        hcps = sqlite_db.query(HCP).all()
        id_map = {}
        for h in hcps:
            new_hcp = HCP(name=h.name, specialty=h.specialty, hospital=h.hospital, email=h.email)
            pg_db.add(new_hcp)
            pg_db.flush()  # get new_hcp.id without committing yet
            id_map[h.id] = new_hcp.id
        pg_db.commit()
        print(f"Migrated {len(hcps)} HCP records.")

        interactions = sqlite_db.query(Interaction).all()
        for i in interactions:
            new_interaction = Interaction(
                hcp_id=id_map[i.hcp_id],
                interaction_type=i.interaction_type,
                date=i.date,
                time=i.time,
                attendees=i.attendees,
                topics_discussed=i.topics_discussed,
                materials_shared=i.materials_shared,
                sentiment=i.sentiment,
                created_at=i.created_at,
            )
            pg_db.add(new_interaction)
        pg_db.commit()
        print(f"Migrated {len(interactions)} interaction records.")
        print("Migration complete.")
    finally:
        sqlite_db.close()
        pg_db.close()


if __name__ == "__main__":
    main()
