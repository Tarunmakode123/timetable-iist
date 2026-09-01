import os
import hashlib
from sqlalchemy import create_engine, Column, String, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from sqlalchemy.pool import NullPool

import shutil

# Search multiple potential paths for the bundled timetable.db file (essential for Vercel packaging)
potential_paths = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "timetable.db"),
    os.path.join(os.getcwd(), "timetable.db"),
    "/var/task/timetable.db",
    "/var/task/api/timetable.db",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "timetable.db")
]

def find_orig_db():
    for path in potential_paths:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "timetable.db")

ORIG_DB_PATH = find_orig_db()
_DB_PREPARED = False

def ensure_db_prepared():
    global _DB_PREPARED, ORIG_DB_PATH
    if os.environ.get("VERCEL"):
        db_tmp = "/tmp/timetable.db"
        if _DB_PREPARED and os.path.exists(db_tmp) and os.path.getsize(db_tmp) > 0:
            return db_tmp
        if not os.path.exists(db_tmp) or os.path.getsize(db_tmp) == 0:
            orig = find_orig_db()
            if orig and os.path.exists(orig) and os.path.getsize(orig) > 0:
                try:
                    os.makedirs(os.path.dirname(db_tmp), exist_ok=True)
                    shutil.copy(orig, db_tmp)
                except Exception as e:
                    print(f"Error copying DB to /tmp: {e}")
        _DB_PREPARED = True
        return db_tmp
    return ORIG_DB_PATH

DB_PATH = ensure_db_prepared()
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 30}, poolclass=NullPool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Helper for password hashing
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

class User(Base):
    __tablename__ = "users"
    username = Column(String, primary_key=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 'admin' or 'faculty'
    faculty_id = Column(String, ForeignKey("faculty.id"), nullable=True)
    
    faculty = relationship("Faculty", back_populates="users")

class Faculty(Base):
    __tablename__ = "faculty"
    id = Column(String, primary_key=True)  # clean name string
    full_name = Column(String, nullable=False)
    known_initials = Column(String, nullable=True)  # comma separated
    department = Column(String, nullable=True)
    max_weekly_hours = Column(Integer, default=16)

    users = relationship("User", back_populates="faculty")
    assignments = relationship("Assignment", back_populates="faculty")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(String, primary_key=True)  # subject_code
    code = Column(String, nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # 'theory' or 'lab'
    weekly_hours = Column(Integer, nullable=False)
    department = Column(String, nullable=True)

    assignments = relationship("Assignment", back_populates="subject")

class Section(Base):
    __tablename__ = "sections"
    id = Column(String, primary_key=True)  # section_id, e.g. CS_1_II
    name = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    department = Column(String, nullable=False)

    batches = relationship("Batch", back_populates="section", cascade="all, delete-orphan")
    assignments = relationship("Assignment", back_populates="section")

class Batch(Base):
    __tablename__ = "batches"
    id = Column(String, primary_key=True)  # e.g. CS_1_II_B1
    section_id = Column(String, ForeignKey("sections.id"), nullable=False)
    label = Column(String, nullable=False)  # e.g. B1, B2

    section = relationship("Section", back_populates="batches")
    assignments = relationship("Assignment", back_populates="batch")

class Room(Base):
    __tablename__ = "rooms"
    id = Column(String, primary_key=True)  # room_name, e.g. LAB-2, SH-2
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # 'classroom', 'lab', 'seminar_hall', 'other'
    capacity = Column(Integer, nullable=True)

    assignments = relationship("Assignment", back_populates="room")

class TimeSlot(Base):
    __tablename__ = "timeslots"
    id = Column(String, primary_key=True)  # e.g. Monday_1
    day = Column(String, nullable=False)  # 'Monday'...'Saturday'
    start_time = Column(String, nullable=False)  # HH:MM
    end_time = Column(String, nullable=False)  # HH:MM

    assignments = relationship("Assignment", back_populates="timeslot")

class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    faculty_id = Column(String, ForeignKey("faculty.id"), nullable=False)
    subject_id = Column(String, ForeignKey("subjects.id"), nullable=False)
    section_id = Column(String, ForeignKey("sections.id"), nullable=True)
    batch_id = Column(String, ForeignKey("batches.id"), nullable=True)
    room_id = Column(String, ForeignKey("rooms.id"), nullable=False)
    timeslot_id = Column(String, ForeignKey("timeslots.id"), nullable=False)
    effective_from = Column(String, nullable=False)  # YYYY-MM-DD
    effective_to = Column(String, nullable=True)  # YYYY-MM-DD, NULL=ongoing
    source = Column(String, nullable=False)  # 'csv', 'legacy', 'manual', 'solver', 'ai_assistant'

    faculty = relationship("Faculty", back_populates="assignments")
    subject = relationship("Subject", back_populates="assignments")
    section = relationship("Section", back_populates="assignments")
    batch = relationship("Batch", back_populates="assignments")
    room = relationship("Room", back_populates="assignments")
    timeslot = relationship("TimeSlot", back_populates="assignments")

class LoadDistribution(Base):
    __tablename__ = "load_distribution"
    id = Column(Integer, primary_key=True, autoincrement=True)
    faculty_name = Column(String, nullable=False)
    semester = Column(String, nullable=True)
    section_name = Column(String, nullable=True)
    subject_name = Column(String, nullable=True)
    theory_hours = Column(Float, default=0.0)
    practical_hours = Column(Float, default=0.0)
    total_hours = Column(Float, default=0.0)

def init_db():
    ensure_db_prepared()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Seed canonical timeslots
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        canonical_slots = [
            ("1", "09:30", "10:20"),
            ("2", "10:20", "11:10"),
            ("3", "11:10", "12:00"),
            ("4", "12:00", "12:50"),
            ("5", "12:50", "13:40"),  # Lunch Slot
            ("6", "13:40", "14:30"),
            ("7", "14:30", "15:20"),
            ("8", "15:20", "16:00")
        ]
        
        # Check if slots are already seeded
        existing_slots = db.query(TimeSlot).count()
        if existing_slots == 0:
            for day in days:
                for s_num, start, end in canonical_slots:
                    slot = TimeSlot(
                        id=f"{day}_{s_num}",
                        day=day,
                        start_time=start,
                        end_time=end
                    )
                    db.add(slot)
            db.commit()
        
        # Seed default admin user if not exists
        admin_exists = db.query(User).filter(User.username == "admin").first()
        if not admin_exists:
            admin_user = User(
                username="admin",
                hashed_password=hash_password("admin123"),
                role="admin"
            )
            db.add(admin_user)
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"init_db error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized and seeded.")
