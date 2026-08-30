import os
import hmac
import hashlib
import csv
from io import StringIO
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, status, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.database import (
    SessionLocal, init_db, Faculty, Subject, Section, Batch, Room, TimeSlot, Assignment, LoadDistribution, User, hash_password
)
from backend.validator import validate_all
from backend.parser import seed_legacy_data

# Secret key for signature token auth
SECRET_KEY = b"timetable-assistant-secret-key-12345"

app = FastAPI(title="Timetable Assistant API")

# Ensure database tables exist and admin user is seeded on startup (essential for Vercel)
init_db()
db_init = SessionLocal()
try:
    admin_exists = db_init.query(User).filter(User.username == "admin").first()
    if not admin_exists:
        admin = User(
            username="admin",
            hashed_password=hash_password("admin123"),
            role="admin"
        )
        db_init.add(admin)
        db_init.commit()
finally:
    db_init.close()

# Setup CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Token utility functions
def create_token(username: str, role: str) -> str:
    payload = f"{username}:{role}"
    sig = hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"

def verify_token(token: str):
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None
        username, role, sig = parts[0], parts[1], parts[2]
        expected_sig = hmac.new(SECRET_KEY, f"{username}:{role}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return {"username": username, "role": role}
    except Exception:
        pass
    return None

# Dependency to get current user from Authorization header
def get_current_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header missing")
    
    try:
        token_type, token = authorization.split(" ")
        if token_type.lower() != "bearer":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization header format")
        
    user_payload = verify_token(token)
    if not user_payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
        
    user = db.query(User).filter(User.username == user_payload["username"]).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin permissions required")
    return current_user

# Pydantic Schemas
class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str # 'admin' or 'faculty'
    faculty_id: Optional[str] = None

class AssignmentCreate(BaseModel):
    faculty_id: str
    subject_id: str
    section_id: Optional[str] = None
    batch_id: Optional[str] = None
    room_id: str
    timeslot_id: str
    effective_from: str
    effective_to: Optional[str] = None

class FacultyCreate(BaseModel):
    id: str
    full_name: str
    known_initials: Optional[str] = None
    department: Optional[str] = None
    max_weekly_hours: Optional[int] = 16

class SubjectCreate(BaseModel):
    id: str
    code: str
    name: str
    type: str # 'theory' or 'lab'
    weekly_hours: int
    department: Optional[str] = None

class RoomCreate(BaseModel):
    id: str
    name: str
    type: str # 'classroom' or 'lab'
    capacity: int

class SectionCreate(BaseModel):
    id: str
    name: str
    year: int
    department: str

# ----------------- Auth Routes -----------------

@app.post("/api/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    user_exists = db.query(User).filter(User.username == req.username).first()
    if user_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
        
    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        role=req.role,
        faculty_id=req.faculty_id
    )
    db.add(user)
    db.commit()
    return {"message": "User registered successfully"}

@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or user.hashed_password != hash_password(req.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
        
    token = create_token(user.username, user.role)
    return {
        "token": token,
        "username": user.username,
        "role": user.role,
        "faculty_id": user.faculty_id
    }

@app.get("/api/auth/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "username": user.username,
        "role": user.role,
        "faculty_id": user.faculty_id
    }

# ----------------- Seed & DB init -----------------

@app.post("/api/admin/seed-legacy", dependencies=[Depends(require_admin)])
def trigger_legacy_seeding(db: Session = Depends(get_db)):
    files = {
        "II Year_TT": r"C:\Users\tarun\Downloads\II Year_TT_July-Dec 24.xlsx",
        "III Year_TT": r"C:\Users\tarun\Downloads\III Year_TT_July-Dec 24 (2).xlsx",
        "Individual_Faculty": r"C:\Users\tarun\Downloads\Individual Faculty Wise Time Table July-Dec 2024 (1).xlsx",
        "Lab_Wise": r"C:\Users\tarun\Downloads\Lab Wise Time Table (1) (2).xlsx",
        "Load_Distribution": r"C:\Users\tarun\Downloads\Load Distribution_2024 (2).xlsx"
    }
    
    # Check if all files exist
    missing = [k for k, p in files.items() if not os.path.exists(p)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Seeding source files missing: {', '.join(missing)}"
        )
        
    try:
        count = seed_legacy_data(db, files)
        return {"message": "Database seeded from legacy spreadsheets successfully!", "count": count}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# ----------------- Validation Route -----------------

@app.get("/api/conflicts")
def get_conflicts(db: Session = Depends(get_db)):
    conflicts = validate_all(db)
    return {
        "summary": {
            "total": len(conflicts),
            "errors": len([c for c in conflicts if c["severity"] == "error"]),
            "warnings": len([c for c in conflicts if c["severity"] == "warning"])
        },
        "conflicts": conflicts
    }

# ----------------- CRUD Routes -----------------

# 1. Faculty
@app.get("/api/faculty")
def get_faculty(db: Session = Depends(get_db)):
    return db.query(Faculty).all()

@app.post("/api/faculty", dependencies=[Depends(require_admin)])
def create_faculty(req: FacultyCreate, db: Session = Depends(get_db)):
    if db.query(Faculty).filter(Faculty.id == req.id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Faculty ID already exists")
    fac = Faculty(**req.dict())
    db.add(fac)
    db.commit()
    return fac

@app.put("/api/faculty/{fac_id}", dependencies=[Depends(require_admin)])
def update_faculty(fac_id: str, req: FacultyCreate, db: Session = Depends(get_db)):
    fac = db.query(Faculty).filter(Faculty.id == fac_id).first()
    if not fac:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faculty not found")
    for k, v in req.dict().items():
        setattr(fac, k, v)
    db.commit()
    return fac

@app.delete("/api/faculty/{fac_id}", dependencies=[Depends(require_admin)])
def delete_faculty(fac_id: str, db: Session = Depends(get_db)):
    fac = db.query(Faculty).filter(Faculty.id == fac_id).first()
    if not fac:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faculty not found")
    db.delete(fac)
    db.commit()
    return {"message": "Faculty deleted successfully"}

# 2. Subjects
@app.get("/api/subjects")
def get_subjects(db: Session = Depends(get_db)):
    return db.query(Subject).all()

@app.post("/api/subjects", dependencies=[Depends(require_admin)])
def create_subject(req: SubjectCreate, db: Session = Depends(get_db)):
    if db.query(Subject).filter(Subject.id == req.id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subject ID already exists")
    sub = Subject(**req.dict())
    db.add(sub)
    db.commit()
    return sub

@app.put("/api/subjects/{sub_id}", dependencies=[Depends(require_admin)])
def update_subject(sub_id: str, req: SubjectCreate, db: Session = Depends(get_db)):
    sub = db.query(Subject).filter(Subject.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    for k, v in req.dict().items():
        setattr(sub, k, v)
    db.commit()
    return sub

@app.delete("/api/subjects/{sub_id}", dependencies=[Depends(require_admin)])
def delete_subject(sub_id: str, db: Session = Depends(get_db)):
    sub = db.query(Subject).filter(Subject.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    db.delete(sub)
    db.commit()
    return {"message": "Subject deleted successfully"}

# 3. Rooms
@app.get("/api/rooms")
def get_rooms(db: Session = Depends(get_db)):
    return db.query(Room).all()

@app.post("/api/rooms", dependencies=[Depends(require_admin)])
def create_room(req: RoomCreate, db: Session = Depends(get_db)):
    if db.query(Room).filter(Room.id == req.id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Room ID already exists")
    room = Room(**req.dict())
    db.add(room)
    db.commit()
    return room

@app.put("/api/rooms/{room_id}", dependencies=[Depends(require_admin)])
def update_room(room_id: str, req: RoomCreate, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    for k, v in req.dict().items():
        setattr(room, k, v)
    db.commit()
    return room

@app.delete("/api/rooms/{room_id}", dependencies=[Depends(require_admin)])
def delete_room(room_id: str, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    db.delete(room)
    db.commit()
    return {"message": "Room deleted successfully"}

# 4. Sections & Batches
@app.get("/api/sections")
def get_sections(db: Session = Depends(get_db)):
    res = []
    for s in db.query(Section).all():
        batches = db.query(Batch).filter(Batch.section_id == s.id).all()
        res.append({
            "id": s.id,
            "name": s.name,
            "year": s.year,
            "department": s.department,
            "batches": [{"id": b.id, "label": b.label} for b in batches]
        })
    return res

@app.post("/api/sections", dependencies=[Depends(require_admin)])
def create_section(req: SectionCreate, db: Session = Depends(get_db)):
    if db.query(Section).filter(Section.id == req.id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Section ID already exists")
    sec = Section(**req.dict())
    db.add(sec)
    db.commit()
    
    # Automatically create B1 & B2 batches
    for label in ["B1", "B2"]:
        batch = Batch(id=f"{sec.id}_{label}", section_id=sec.id, label=label)
        db.add(batch)
    db.commit()
    return sec

@app.delete("/api/sections/{sec_id}", dependencies=[Depends(require_admin)])
def delete_section(sec_id: str, db: Session = Depends(get_db)):
    sec = db.query(Section).filter(Section.id == sec_id).first()
    if not sec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")
    db.query(Batch).filter(Batch.section_id == sec_id).delete()
    db.delete(sec)
    db.commit()
    return {"message": "Section and associated batches deleted"}

# 5. Assignments
@app.get("/api/assignments")
def get_assignments(db: Session = Depends(get_db)):
    return db.query(Assignment).all()

@app.post("/api/assignments", dependencies=[Depends(require_admin)])
def create_assignment(req: AssignmentCreate, db: Session = Depends(get_db)):
    # Validate timeslot
    if not db.query(TimeSlot).filter(TimeSlot.id == req.timeslot_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid timeslot")
    # Validate references
    if not db.query(Faculty).filter(Faculty.id == req.faculty_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Faculty ID not found")
    if not db.query(Subject).filter(Subject.id == req.subject_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subject ID not found")
    if not db.query(Room).filter(Room.id == req.room_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Room ID not found")
    if req.section_id and not db.query(Section).filter(Section.id == req.section_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Section ID not found")
    if req.batch_id and not db.query(Batch).filter(Batch.id == req.batch_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Batch ID not found")

    assign = Assignment(**req.dict())
    db.add(assign)
    db.commit()
    return assign

@app.put("/api/assignments/{assign_id}", dependencies=[Depends(require_admin)])
def update_assignment(assign_id: int, req: AssignmentCreate, db: Session = Depends(get_db)):
    assign = db.query(Assignment).filter(Assignment.id == assign_id).first()
    if not assign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
        
    for k, v in req.dict().items():
        setattr(assign, k, v)
    db.commit()
    return assign

@app.delete("/api/assignments/{assign_id}", dependencies=[Depends(require_admin)])
def delete_assignment(assign_id: int, db: Session = Depends(get_db)):
    assign = db.query(Assignment).filter(Assignment.id == assign_id).first()
    if not assign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    db.delete(assign)
    db.commit()
    return {"message": "Assignment deleted successfully"}

# ----------------- CSV Import/Preview/Commit -----------------

@app.post("/api/csv/preview", dependencies=[Depends(require_admin)])
async def upload_csv_preview(file: UploadFile = File(...), type: str = Form(...)):
    content = await file.read()
    decoded = content.decode('utf-8')
    f = StringIO(decoded)
    reader = csv.DictReader(f)
    
    records = []
    errors = []
    
    # Process line-by-line
    for i, row in enumerate(reader):
        line_num = i + 1
        record = dict(row)
        
        # Basic validation depending on type
        if type == "assignments":
            req_cols = ["faculty_id", "subject_id", "room_id", "timeslot_id", "effective_from"]
            missing = [col for col in req_cols if col not in record or not record[col].strip()]
            if missing:
                errors.append(f"Row {line_num}: Missing column(s): {', '.join(missing)}")
            else:
                records.append({
                    "faculty_id": record["faculty_id"].strip(),
                    "subject_id": record["subject_id"].strip(),
                    "section_id": record.get("section_id", "").strip() or None,
                    "batch_id": record.get("batch_id", "").strip() or None,
                    "room_id": record["room_id"].strip(),
                    "timeslot_id": record["timeslot_id"].strip(),
                    "effective_from": record["effective_from"].strip(),
                    "effective_to": record.get("effective_to", "").strip() or None
                })
        elif type == "faculty":
            req_cols = ["id", "full_name"]
            missing = [col for col in req_cols if col not in record or not record[col].strip()]
            if missing:
                errors.append(f"Row {line_num}: Missing column(s): {', '.join(missing)}")
            else:
                records.append({
                    "id": record["id"].strip(),
                    "full_name": record["full_name"].strip(),
                    "known_initials": record.get("known_initials", "").strip() or None,
                    "department": record.get("department", "").strip() or None,
                    "max_weekly_hours": int(record.get("max_weekly_hours", "16").strip() or "16")
                })
        elif type == "subjects":
            req_cols = ["id", "code", "name", "type", "weekly_hours"]
            missing = [col for col in req_cols if col not in record or not record[col].strip()]
            if missing:
                errors.append(f"Row {line_num}: Missing column(s): {', '.join(missing)}")
            else:
                records.append({
                    "id": record["id"].strip(),
                    "code": record["code"].strip(),
                    "name": record["name"].strip(),
                    "type": record["type"].strip(),
                    "weekly_hours": int(record["weekly_hours"].strip() or "4"),
                    "department": record.get("department", "").strip() or None
                })
        elif type == "rooms":
            req_cols = ["id", "name", "type", "capacity"]
            missing = [col for col in req_cols if col not in record or not record[col].strip()]
            if missing:
                errors.append(f"Row {line_num}: Missing column(s): {', '.join(missing)}")
            else:
                records.append({
                    "id": record["id"].strip(),
                    "name": record["name"].strip(),
                    "type": record["type"].strip(),
                    "capacity": int(record["capacity"].strip() or "60")
                })
        else:
            errors.append("Invalid CSV Import Type")
            break
            
    return {
        "filename": file.filename,
        "type": type,
        "total_rows": len(records) + len(errors),
        "valid_count": len(records),
        "error_count": len(errors),
        "errors": errors,
        "preview": records[:50] # Limit preview rows
    }

@app.post("/api/csv/commit", dependencies=[Depends(require_admin)])
def commit_csv_import(req: dict, db: Session = Depends(get_db)):
    type = req.get("type")
    records = req.get("records", [])
    
    if not type or not records:
        raise HTTPException(status_code=400, detail="Missing import type or records")
        
    committed_count = 0
    
    try:
        if type == "assignments":
            for r in records:
                # Upsert/Insert assignment
                assign = Assignment(
                    faculty_id=r["faculty_id"],
                    subject_id=r["subject_id"],
                    section_id=r.get("section_id"),
                    batch_id=r.get("batch_id"),
                    room_id=r["room_id"],
                    timeslot_id=r["timeslot_id"],
                    effective_from=r["effective_from"],
                    effective_to=r.get("effective_to")
                )
                db.add(assign)
                committed_count += 1
        elif type == "faculty":
            for r in records:
                fac = db.query(Faculty).filter(Faculty.id == r["id"]).first()
                if fac:
                    for k, v in r.items():
                        setattr(fac, k, v)
                else:
                    db.add(Faculty(**r))
                committed_count += 1
        elif type == "subjects":
            for r in records:
                sub = db.query(Subject).filter(Subject.id == r["id"]).first()
                if sub:
                    for k, v in r.items():
                        setattr(sub, k, v)
                else:
                    db.add(Subject(**r))
                committed_count += 1
        elif type == "rooms":
            for r in records:
                room = db.query(Room).filter(Room.id == r["id"]).first()
                if room:
                    for k, v in r.items():
                        setattr(room, k, v)
                else:
                    db.add(Room(**r))
                committed_count += 1
        else:
            raise HTTPException(status_code=400, detail="Invalid import type")
            
        db.commit()
        return {"message": f"Successfully imported {committed_count} records.", "count": committed_count}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# ----------------- TimeSlots Route -----------------

@app.get("/api/timeslots")
def get_timeslots(db: Session = Depends(get_db)):
    return db.query(TimeSlot).all()

from fastapi.responses import FileResponse

@app.get("/")
@app.get("/{full_path:path}")
async def serve_frontend(full_path: str = ""):
    if full_path.startswith("api"):
        raise HTTPException(status_code=404, detail="API route not found")
    index_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "index.html not found"}

if __name__ == "__main__":
    import uvicorn
    init_db()
    # Create default admin user if not exists
    db = SessionLocal()
    admin_exists = db.query(User).filter(User.username == "admin").first()
    if not admin_exists:
        admin = User(
            username="admin",
            hashed_password=hash_password("admin123"),
            role="admin"
        )
        db.add(admin)
        db.commit()
    db.close()
    
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
