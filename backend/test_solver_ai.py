import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, Faculty, Subject, Section, Batch, Room, TimeSlot, Assignment, LoadDistribution, User, hash_password
from backend.solver import solve_timetable
from backend.ai_assistant import process_ai_request

# In-memory SQLite database for testing
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    # Seed minimal test data
    f1 = Faculty(id="FAC_VIMMY", full_name="Ms. Vimmy", known_initials="VK", department="CS", max_weekly_hours=16)
    f2 = Faculty(id="FAC_NEERAJ", full_name="Dr. Neeraj", known_initials="NK", department="CS", max_weekly_hours=16)

    sub1 = Subject(id="SUB_CS201", code="CS201", name="Data Structures", type="theory", weekly_hours=3, department="CS")
    sub2 = Subject(id="SUB_CS202", code="CS202", name="Data Structures Lab", type="lab", weekly_hours=2, department="CS")

    sec1 = Section(id="SEC_CS1", name="CS-1", year=2, department="CS")
    b1 = Batch(id="SEC_CS1_B1", section_id="SEC_CS1", label="B1")
    b2 = Batch(id="SEC_CS1_B2", section_id="SEC_CS1", label="B2")

    r1 = Room(id="R201", name="Classroom 201", type="classroom", capacity=60)
    r2 = Room(id="LAB1", name="Computer Lab 1", type="lab", capacity=30)
    r3 = Room(id="LAB2", name="Computer Lab 2", type="lab", capacity=30)

    # Timeslots: Monday 1-4, Tuesday 1-4
    ts_list = []
    days = ["Monday", "Tuesday"]
    for day in days:
        for p in range(1, 5):
            ts = TimeSlot(id=f"{day}_{p}", day=day, start_time=f"0{8+p}:30", end_time=f"0{9+p}:20")
            ts_list.append(ts)

    session.add_all([f1, f2, sub1, sub2, sec1, b1, b2, r1, r2, r3] + ts_list)

    ld1 = LoadDistribution(
        faculty_name="Ms. Vimmy",
        semester="CS201",
        section_name="CS-1",
        subject_name="Data Structures",
        theory_hours=2,
        practical_hours=0,
        total_hours=2
    )
    ld2 = LoadDistribution(
        faculty_name="Dr. Neeraj",
        semester="CS202",
        section_name="CS-1",
        subject_name="Data Structures Lab",
        theory_hours=0,
        practical_hours=1,
        total_hours=1
    )
    session.add_all([ld1, ld2])
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)

def test_cpsat_solver_generation(db_session):
    """Test OR-Tools CP-SAT solver generates conflict-free assignments."""
    result = solve_timetable(db_session)
    assert result["status"] == "success"
    assert len(result["assignments"]) >= 3 # 2 theory + 2 batch-split lab slots

def test_ai_query_mode(db_session):
    """Test AI assistant natural-language query mode."""
    assign1 = Assignment(
        faculty_id="FAC_VIMMY",
        subject_id="SUB_CS201",
        section_id="SEC_CS1",
        room_id="R201",
        timeslot_id="Tuesday_1",
        effective_from="2026-08-30",
        source="manual"
    )
    db_session.add(assign1)
    db_session.commit()

    res = process_ai_request("What is Ms. Vimmy's Tuesday schedule?", db_session)
    assert res["mode"] == "query"
    assert "Ms. Vimmy" in res["text"]
    assert "Tuesday_1" in res["text"]

def test_ai_action_move_valid(db_session):
    """Test AI assistant proposed move when slot is free."""
    assign1 = Assignment(
        faculty_id="FAC_NEERAJ",
        subject_id="SUB_CS201",
        section_id="SEC_CS1",
        room_id="R201",
        timeslot_id="Monday_2",
        effective_from="2026-08-30",
        source="manual"
    )
    db_session.add(assign1)
    db_session.commit()

    res = process_ai_request("Move Dr. Neeraj's Monday P2 class to Tuesday P3", db_session)
    assert res["mode"] == "action"
    assert res["status"] == "valid"
    assert res["diff"]["to_add"][0]["timeslot_id"] == "Tuesday_3"

def test_ai_action_move_conflict_alternatives(db_session):
    """Test AI assistant detecting double booking and proposing alternative slots."""
    assign1 = Assignment(
        faculty_id="FAC_NEERAJ",
        subject_id="SUB_CS201",
        section_id="SEC_CS1",
        room_id="R201",
        timeslot_id="Monday_2",
        effective_from="2026-08-30",
        source="manual"
    )
    # Another class occupying R201 on Tuesday P3
    assign2 = Assignment(
        faculty_id="FAC_VIMMY",
        subject_id="SUB_CS201",
        section_id="SEC_CS1",
        room_id="R201",
        timeslot_id="Tuesday_3",
        effective_from="2026-08-30",
        source="manual"
    )
    db_session.add_all([assign1, assign2])
    db_session.commit()

    res = process_ai_request("Move Dr. Neeraj's Monday P2 class to Tuesday P3", db_session)
    assert res["mode"] == "action"
    assert res["status"] == "conflict"
    assert len(res["alternatives"]) > 0
