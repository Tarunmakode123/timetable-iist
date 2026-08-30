from sqlalchemy.orm import Session
from .database import Assignment, Faculty, Subject, Room, TimeSlot, Section, Batch, LoadDistribution
from datetime import datetime

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None

def dates_overlap(from1, to1, from2, to2):
    # from1, to1, from2, to2 are YYYY-MM-DD strings. NULL/None means infinity.
    # Convert to dates or large/small date limits
    d_from1 = parse_date(from1) or datetime.min.date()
    d_to1 = parse_date(to1) or datetime.max.date()
    d_from2 = parse_date(from2) or datetime.min.date()
    d_to2 = parse_date(to2) or datetime.max.date()
    return d_from1 <= d_to2 and d_from2 <= d_to1

def get_parent_section(db: Session, assignment: Assignment):
    if assignment.section_id:
        return assignment.section_id
    if assignment.batch_id:
        batch = db.query(Batch).filter(Batch.id == assignment.batch_id).first()
        if batch:
            return batch.section_id
    return None

def clean_name(name):
    if not name:
        return ""
    name = str(name).lower()
    for prefix in ["dr. (mrs.)", "dr. (ms.)", "dr.", "mr.", "ms.", "mrs.", "prof."]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.replace(".", "").replace(" ", "").strip()

def match_faculty_names(name_ld, name_fac, initials_fac):
    cleaned_ld = clean_name(name_ld)
    cleaned_fac = clean_name(name_fac)
    
    if not cleaned_ld or not cleaned_fac:
        return False
        
    # Direct match
    if cleaned_ld == cleaned_fac:
        return True
    
    # Substring match
    if cleaned_fac in cleaned_ld or cleaned_ld in cleaned_fac:
        return True
        
    # Initials check
    if initials_fac:
        initials_list = [i.strip().lower() for i in initials_fac.split(",") if i.strip()]
        for initial in initials_list:
            if initial and initial in cleaned_ld:
                return True
                
    return False

def validate_all(db: Session):
    conflicts = []
    
    # 1. Fetch all data
    assignments = db.query(Assignment).all()
    faculties = db.query(Faculty).all()
    subjects = db.query(Subject).all()
    rooms = db.query(Room).all()
    timeslots = db.query(TimeSlot).all()
    sections = db.query(Section).all()
    batches = db.query(Batch).all()
    load_entries = db.query(LoadDistribution).all()
    
    # Pre-map parent sections for speed
    assignment_parent_sections = {}
    for a in assignments:
        assignment_parent_sections[a.id] = get_parent_section(db, a)
        
    # Pre-map room types
    room_types = {r.id: r.type for r in rooms}
    
    # 2. Check Faculty Double-Booking and Room Double-Booking
    # We do a pairwise comparison of all assignments
    for i in range(len(assignments)):
        a1 = assignments[i]
        p_sec1 = assignment_parent_sections[a1.id]
        for j in range(i + 1, len(assignments)):
            a2 = assignments[j]
            
            # Check if they overlap in timeslot and date range
            if a1.timeslot_id == a2.timeslot_id and dates_overlap(a1.effective_from, a1.effective_to, a2.effective_from, a2.effective_to):
                # 2.a Faculty Double-Booking
                # Overlap on same timeslot and dates for the same faculty
                if a1.faculty_id == a2.faculty_id:
                    # Ignore if they are co-teaching the exact same class/subject/room
                    is_co_taught = (
                        a1.room_id == a2.room_id and
                        a1.subject_id == a2.subject_id and
                        p_sec1 == assignment_parent_sections[a2.id]
                    )
                    if not is_co_taught:
                        conflicts.append({
                            "type": "faculty_double_booking",
                            "severity": "error",
                            "message": f"Faculty '{a1.faculty_id}' is double-booked on {a1.timeslot_id.split('_')[0]} Period {a1.timeslot_id.split('_')[1]} between Section '{p_sec1}' (Room {a1.room_id}) and Section '{assignment_parent_sections[a2.id]}' (Room {a2.room_id}).",
                            "affected_ids": [a1.id, a2.id],
                            "details": {
                                "faculty_id": a1.faculty_id,
                                "timeslot_id": a1.timeslot_id,
                                "day": a1.timeslot_id.split('_')[0],
                                "period": a1.timeslot_id.split('_')[1]
                            }
                        })
                
                # 2.b Room Double-Booking
                # Overlap on same timeslot and dates for the same room
                if a1.room_id == a2.room_id:
                    # Ignore if they are parallel batches of the SAME section in a lab room
                    p_sec2 = assignment_parent_sections[a2.id]
                    is_parallel_lab_split = (
                        p_sec1 == p_sec2 and
                        p_sec1 is not None and
                        room_types.get(a1.room_id) == "lab"
                    )
                    
                    if not is_parallel_lab_split:
                        conflicts.append({
                            "type": "room_double_booking",
                            "severity": "error",
                            "message": f"Room '{a1.room_id}' is double-booked on {a1.timeslot_id.split('_')[0]} Period {a1.timeslot_id.split('_')[1]} by Section '{p_sec1}' and Section '{p_sec2}'.",
                            "affected_ids": [a1.id, a2.id],
                            "details": {
                                "room_id": a1.room_id,
                                "timeslot_id": a1.timeslot_id,
                                "day": a1.timeslot_id.split('_')[0],
                                "period": a1.timeslot_id.split('_')[1]
                            }
                        })
                
                # 2.c Section Student Double-Booking (Bonus Safeguard)
                if p_sec1 == assignment_parent_sections[a2.id] and p_sec1 is not None:
                    # Overlap for the same section
                    # Ignore if they are different batches of the same section in different rooms (e.g. lab split)
                    is_batch_split = (
                        a1.batch_id != a2.batch_id and
                        a1.batch_id is not None and
                        a2.batch_id is not None and
                        a1.room_id != a2.room_id
                    )
                    # Also ignore if duplicate identical assignments
                    is_identical = (
                        a1.subject_id == a2.subject_id and
                        a1.room_id == a2.room_id and
                        a1.faculty_id == a2.faculty_id
                    )
                    if not is_batch_split and not is_identical:
                        conflicts.append({
                            "type": "section_double_booking",
                            "severity": "error",
                            "message": f"Section '{p_sec1}' is double-booked on {a1.timeslot_id.split('_')[0]} Period {a1.timeslot_id.split('_')[1]} for Subject '{a1.subject_id}' and Subject '{a2.subject_id}'.",
                            "affected_ids": [a1.id, a2.id],
                            "details": {
                                "section_id": p_sec1,
                                "timeslot_id": a1.timeslot_id,
                                "day": a1.timeslot_id.split('_')[0],
                                "period": a1.timeslot_id.split('_')[1]
                            }
                        })

    # 3. Faculty Over Max Weekly Hours
    # We must evaluate hours within active periods.
    # To be general, we can check for each unique effective_from date.
    active_dates = sorted(list(set([a.effective_from for a in assignments])))
    if not active_dates:
        active_dates = ["2026-08-30"] # Fallback to today
        
    for date_str in active_dates:
        # Sum hours for each faculty on this date
        fac_hours = {}
        for a in assignments:
            if parse_date(a.effective_from) <= parse_date(date_str) and (a.effective_to is None or parse_date(a.effective_to) >= parse_date(date_str)):
                # Each slot taught counts as 1 hour
                fac_hours[a.faculty_id] = fac_hours.get(a.faculty_id, 0) + 1
                
        for f in faculties:
            hours = fac_hours.get(f.id, 0)
            if hours > f.max_weekly_hours:
                conflicts.append({
                    "type": "faculty_over_hours",
                    "severity": "warning",
                    "message": f"Faculty '{f.full_name}' ({f.id}) exceeds max weekly hours ({f.max_weekly_hours}) with {hours} scheduled hours on date version '{date_str}'.",
                    "affected_ids": [f.id],
                    "details": {
                        "faculty_id": f.id,
                        "faculty_name": f.full_name,
                        "scheduled_hours": hours,
                        "max_hours": f.max_weekly_hours,
                        "date_version": date_str
                    }
                })

    # 4. Load Distribution Reconciliation ("unverifiable — data needed")
    # For each entry in LoadDistribution, check if there is any active timetable assignment.
    # We reconcile using fuzzy name matching.
    for entry in load_entries:
        # Match faculty
        matched_faculty = None
        for f in faculties:
            if match_faculty_names(entry.faculty_name, f.full_name, f.known_initials):
                matched_faculty = f
                break
                
        if not matched_faculty:
            conflicts.append({
                "type": "load_mismatch",
                "severity": "warning",
                "message": f"Load entry '{entry.faculty_name}' teaching '{entry.subject_name}' in section '{entry.section_name}' has no matching Faculty record in the system.",
                "affected_ids": [entry.id],
                "details": {
                    "load_entry_id": entry.id,
                    "faculty_name": entry.faculty_name,
                    "subject_name": entry.subject_name,
                    "section_name": entry.section_name,
                    "reason": "Faculty record missing"
                }
            })
            continue
            
        # Find active assignments matching faculty and section/subject
        matched_assignments = []
        for a in assignments:
            if a.faculty_id == matched_faculty.id:
                # check subject (either code matches or name matches)
                sub = db.query(Subject).filter(Subject.id == a.subject_id).first()
                sub_code = entry.semester.strip() if entry.semester else ""
                
                # Compare subject code or subject name
                sub_match = False
                if sub:
                    # subject code match
                    if sub.code.lower() in sub_code.lower() or sub_code.lower() in sub.code.lower():
                        sub_match = True
                    elif clean_name(sub.name) in clean_name(entry.subject_name) or clean_name(entry.subject_name) in clean_name(sub.name):
                        sub_match = True
                        
                # Compare section
                sec_match = False
                p_sec = assignment_parent_sections.get(a.id)
                if p_sec:
                    # section match, e.g. CS-3 matches CS-3 or IT matches IT
                    cleaned_psec = p_sec.replace("_", "").replace("-", "").replace(" ", "").lower()
                    cleaned_entrysec = entry.section_name.replace("_", "").replace("-", "").replace(" ", "").lower()
                    if cleaned_psec in cleaned_entrysec or cleaned_entrysec in cleaned_psec:
                        sec_match = True
                        
                if sub_match and sec_match:
                    matched_assignments.append(a)
                    
        if not matched_assignments:
            conflicts.append({
                "type": "load_mismatch",
                "severity": "warning",
                "message": f"Load entry '{entry.faculty_name}' -> '{entry.subject_name}' ({entry.section_name}) has no scheduled assignments in the timetable (unverifiable — data needed).",
                "affected_ids": [entry.id],
                "details": {
                    "load_entry_id": entry.id,
                    "faculty_name": entry.faculty_name,
                    "subject_name": entry.subject_name,
                    "section_name": entry.section_name,
                    "reason": "unverifiable — data needed"
                }
            })

    return conflicts
