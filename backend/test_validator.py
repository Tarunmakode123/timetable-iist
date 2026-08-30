import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base, Faculty, Subject, Section, Batch, Room, TimeSlot, Assignment, LoadDistribution
from backend.validator import validate_all

# Setup in-memory SQLite database for testing
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        # Seed basic timeslots
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]:
            for p in range(1, 9):
                db.add(TimeSlot(id=f"{day}_{p}", day=day, start_time="09:30", end_time="10:20"))
        db.commit()
        yield db
    finally:
        db.close()

def test_parallel_lab_no_conflict(db_session):
    db = db_session
    # Seed data: 1 faculty, 1 subject, 1 section, 2 batches, 2 rooms, same timeslot
    f1 = Faculty(id="fac_1", full_name="Faculty One", max_weekly_hours=16)
    sub1 = Subject(id="sub_1", code="SUB1", name="Subject One", type="lab", weekly_hours=4)
    sec1 = Section(id="section_one", name="Section One", year=2, department="CS")
    b1 = Batch(id="section_one_B1", section_id="section_one", label="B1")
    b2 = Batch(id="section_one_B2", section_id="section_one", label="B2")
    r1 = Room(id="lab_1", name="Lab One", type="lab")
    r2 = Room(id="lab_2", name="Lab Two", type="lab")
    
    db.add_all([f1, sub1, sec1, b1, b2, r1, r2])
    db.commit()
    
    # Create two parallel lab assignments: Section One Batch B1 in Lab One, Section One Batch B2 in Lab Two
    f2 = Faculty(id="fac_2", full_name="Faculty Two", max_weekly_hours=16)
    db.add(f2)
    db.commit()
    
    a1 = Assignment(
        faculty_id="fac_1",
        subject_id="sub_1",
        section_id="section_one",
        batch_id="section_one_B1",
        room_id="lab_1",
        timeslot_id="Monday_1",
        effective_from="2026-08-30",
        source="manual"
    )
    a2 = Assignment(
        faculty_id="fac_2",
        subject_id="sub_1",
        section_id="section_one",
        batch_id="section_one_B2",
        room_id="lab_2",
        timeslot_id="Monday_1",
        effective_from="2026-08-30",
        source="manual"
    )
    db.add_all([a1, a2])
    db.commit()
    
    # Run validation
    conflicts = validate_all(db)
    
    # Check that no conflicts are returned for parallel labs
    assert len(conflicts) == 0

def test_room_double_booking(db_session):
    db = db_session
    # Seed data: 2 sections, 1 room, 2 faculty, same timeslot
    f1 = Faculty(id="fac_1", full_name="Faculty One", max_weekly_hours=16)
    f2 = Faculty(id="fac_2", full_name="Faculty Two", max_weekly_hours=16)
    sub1 = Subject(id="sub_1", code="SUB1", name="Subject One", type="theory", weekly_hours=4)
    sec1 = Section(id="section_one", name="Section One", year=2, department="CS")
    sec2 = Section(id="section_two", name="Section Two", year=2, department="CS")
    r1 = Room(id="room_1", name="Room One", type="classroom")
    
    db.add_all([f1, f2, sub1, sec1, sec2, r1])
    db.commit()
    
    a1 = Assignment(
        faculty_id="fac_1",
        subject_id="sub_1",
        section_id="section_one",
        room_id="room_1",
        timeslot_id="Monday_1",
        effective_from="2026-08-30",
        source="manual"
    )
    a2 = Assignment(
        faculty_id="fac_2",
        subject_id="sub_1",
        section_id="section_two",
        room_id="room_1",
        timeslot_id="Monday_1",
        effective_from="2026-08-30",
        source="manual"
    )
    db.add_all([a1, a2])
    db.commit()
    
    conflicts = validate_all(db)
    
    # We should have a room_double_booking conflict
    room_conflicts = [c for c in conflicts if c["type"] == "room_double_booking"]
    assert len(room_conflicts) == 1
    assert "Room 'room_1' is double-booked" in room_conflicts[0]["message"]

def test_faculty_double_booking(db_session):
    db = db_session
    # Seed data: 1 faculty, 2 sections, 2 rooms, same timeslot
    f1 = Faculty(id="fac_1", full_name="Faculty One", max_weekly_hours=16)
    sub1 = Subject(id="sub_1", code="SUB1", name="Subject One", type="theory", weekly_hours=4)
    sec1 = Section(id="section_one", name="Section One", year=2, department="CS")
    sec2 = Section(id="section_two", name="Section Two", year=2, department="CS")
    r1 = Room(id="room_1", name="Room One", type="classroom")
    r2 = Room(id="room_2", name="Room Two", type="classroom")
    
    db.add_all([f1, sub1, sec1, sec2, r1, r2])
    db.commit()
    
    a1 = Assignment(
        faculty_id="fac_1",
        subject_id="sub_1",
        section_id="section_one",
        room_id="room_1",
        timeslot_id="Monday_1",
        effective_from="2026-08-30",
        source="manual"
    )
    a2 = Assignment(
        faculty_id="fac_1",
        subject_id="sub_1",
        section_id="section_two",
        room_id="room_2",
        timeslot_id="Monday_1",
        effective_from="2026-08-30",
        source="manual"
    )
    db.add_all([a1, a2])
    db.commit()
    
    conflicts = validate_all(db)
    
    # We should have a faculty_double_booking conflict
    fac_conflicts = [c for c in conflicts if c["type"] == "faculty_double_booking"]
    assert len(fac_conflicts) == 1
    assert "Faculty 'fac_1' is double-booked" in fac_conflicts[0]["message"]

def test_load_distribution_warnings(db_session):
    db = db_session
    f1 = Faculty(id="fac_1", full_name="Faculty One", known_initials="F1", max_weekly_hours=16)
    sub1 = Subject(id="sub_1", code="SUB1", name="Subject One", type="theory", weekly_hours=4)
    sec1 = Section(id="section_one", name="Section One", year=2, department="CS")
    
    db.add_all([f1, sub1, sec1])
    db.commit()
    
    ld1 = LoadDistribution(
        faculty_name="Faculty One",
        semester="SUB1",
        section_name="Section One",
        subject_name="Subject One",
        theory_hours=4.0,
        practical_hours=0.0,
        total_hours=4.0
    )
    db.add(ld1)
    db.commit()
    
    # Case 1: LoadDistribution entry exists but NO assignments exist
    conflicts = validate_all(db)
    unverified_conflicts = [c for c in conflicts if c["type"] == "load_mismatch" and c["details"].get("reason") == "unverifiable — data needed"]
    assert len(unverified_conflicts) == 1
    assert "unverifiable — data needed" in unverified_conflicts[0]["message"]
    
    # Case 2: Assignment is created, matching the load distribution entry
    a1 = Assignment(
        faculty_id="fac_1",
        subject_id="sub_1",
        section_id="section_one",
        room_id="room_1",
        timeslot_id="Monday_1",
        effective_from="2026-08-30",
        source="manual"
    )
    r1 = Room(id="room_1", name="Room One", type="classroom")
    db.add(r1)
    db.add(a1)
    db.commit()
    
    # Re-run validation: Should match now, so no "unverifiable — data needed" conflicts
    conflicts = validate_all(db)
    unverified_conflicts = [c for c in conflicts if c["type"] == "load_mismatch" and c["details"].get("reason") == "unverifiable — data needed"]
    assert len(unverified_conflicts) == 0
