from sqlalchemy.orm import Session
from backend.database import Assignment, Faculty, Subject, Room, TimeSlot, Section, Batch, LoadDistribution
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

def match_faculty_names(name_ld, name_fac, initials_fac=None):
    if not name_ld or not name_fac:
        return False
    c_ld = clean_name(name_ld)
    c_fac = clean_name(name_fac)
    
    if c_ld == c_fac:
        return True
        
    if initials_fac:
        initials_list = [i.strip().lower() for i in initials_fac.split(",") if i.strip()]
        if c_ld in initials_list:
            return True

    import re
    tokens_ld = set(re.findall(r'\w+', str(name_ld).lower())) - {"mr", "dr", "ms", "mrs", "prof"}
    tokens_fac = set(re.findall(r'\w+', str(name_fac).lower())) - {"mr", "dr", "ms", "mrs", "prof"}
    
    if len(tokens_ld) >= 2 and len(tokens_fac) >= 2:
        return tokens_ld == tokens_fac
        
    if tokens_ld and tokens_fac and tokens_ld.issubset(tokens_fac):
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
    
    # Pre-map parent sections and room types
    assignment_parent_sections = {}
    for a in assignments:
        assignment_parent_sections[a.id] = get_parent_section(db, a)
        
    room_types = {r.id: r.type for r in rooms}
    
    seen_conflict_pairs = set()

    # 2. Check Faculty Double-Booking, Room Double-Booking, and Section Double-Booking
    for i in range(len(assignments)):
        a1 = assignments[i]
        p_sec1 = assignment_parent_sections[a1.id]
        for j in range(i + 1, len(assignments)):
            a2 = assignments[j]
            p_sec2 = assignment_parent_sections[a2.id]
            
            # Check if they overlap in timeslot and date range
            if a1.timeslot_id == a2.timeslot_id and dates_overlap(a1.effective_from, a1.effective_to, a2.effective_from, a2.effective_to):
                
                # Deduplicate identical assignment rows
                is_identical = (
                    a1.faculty_id == a2.faculty_id and
                    a1.subject_id == a2.subject_id and
                    a1.room_id == a2.room_id and
                    p_sec1 == p_sec2 and
                    a1.batch_id == a2.batch_id
                )
                if is_identical:
                    continue

                # Check for legitimate merged/combined lecture (same faculty in same room for multiple sections)
                is_merged_lecture = (a1.faculty_id == a2.faculty_id and a1.room_id == a2.room_id)

                # 2.a Faculty Double-Booking
                # Flagged only if same faculty is assigned to TWO DIFFERENT rooms simultaneously
                if a1.faculty_id == a2.faculty_id and not is_merged_lecture:
                    is_same_class = (p_sec1 == p_sec2 and p_sec1 is not None and a1.room_id == a2.room_id)
                    if not is_same_class and p_sec1 != p_sec2:
                        conflict_key = ("faculty_double_booking", a1.faculty_id, a1.timeslot_id)
                        if conflict_key not in seen_conflict_pairs:
                            seen_conflict_pairs.add(conflict_key)
                            conflicts.append({
                                "type": "faculty_double_booking",
                                "severity": "error",
                                "message": f"Faculty '{a1.faculty_id}' is double-booked on {a1.timeslot_id.split('_')[0]} Period {a1.timeslot_id.split('_')[1]} between Section '{p_sec1}' (Room {a1.room_id}) and Section '{p_sec2}' (Room {a2.room_id}).",
                                "affected_ids": [a1.id, a2.id],
                                "details": {
                                    "faculty_id": a1.faculty_id,
                                    "timeslot_id": a1.timeslot_id,
                                    "day": a1.timeslot_id.split('_')[0],
                                    "period": a1.timeslot_id.split('_')[1]
                                }
                            })
                
                # 2.b Room Double-Booking
                # Flagged only if same room is assigned to TWO DIFFERENT faculties or sections without co-teaching/merging
                if a1.room_id == a2.room_id and not is_merged_lecture:
                    if p_sec1 != p_sec2 and p_sec1 is not None and p_sec2 is not None:
                        conflict_key = ("room_double_booking", a1.room_id, a1.timeslot_id)
                        if conflict_key not in seen_conflict_pairs:
                            seen_conflict_pairs.add(conflict_key)
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
                
                # 2.c Section Student Double-Booking
                # Flagged only if the SAME section is scheduled for conflicting whole-section lectures simultaneously
                if p_sec1 == p_sec2 and p_sec1 is not None:
                    # Recognize valid parallel batch split (e.g. B1 in Room A, B2 in Room B or different labs)
                    is_parallel_batch_split = (
                        (a1.batch_id and a2.batch_id and a1.batch_id != a2.batch_id) or
                        (a1.room_id != a2.room_id) or
                        (room_types.get(a1.room_id) == "lab" or room_types.get(a2.room_id) == "lab") or
                        (a1.subject_id != a2.subject_id)
                    )
                    
                    if not is_parallel_batch_split:
                        conflict_key = ("section_double_booking", p_sec1, a1.timeslot_id)
                        if conflict_key not in seen_conflict_pairs:
                            seen_conflict_pairs.add(conflict_key)
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

    # 3. Faculty Over Max Weekly Hours (Unique Scheduled Timeslots per Faculty)
    fac_slots = {}
    for a in assignments:
        if a.faculty_id:
            if a.faculty_id not in fac_slots:
                fac_slots[a.faculty_id] = set()
            fac_slots[a.faculty_id].add((a.timeslot_id, a.effective_from))
            
    for f in faculties:
        hours = len(fac_slots.get(f.id, set()))
        if hours > f.max_weekly_hours:
            conflicts.append({
                "type": "faculty_over_hours",
                "severity": "warning",
                "message": f"Faculty '{f.full_name}' ({f.id}) exceeds max weekly hours ({f.max_weekly_hours}) with {hours} scheduled hours.",
                "affected_ids": [f.id],
                "details": {
                    "faculty_id": f.id,
                    "faculty_name": f.full_name,
                    "scheduled_hours": hours,
                    "max_hours": f.max_weekly_hours
                }
            })

    # 4. Lunch Period Assignment Conflict (Period 5 - 12:50 to 13:40)
    for a in assignments:
        if a.timeslot_id.endswith("_5"):
            conflicts.append({
                "type": "LUNCH_PERIOD_VIOLATION",
                "severity": "hard",
                "message": f"Assignment #{a.id} ({a.subject_id}) is invalidly scheduled during Period 5 lunch break ({a.timeslot_id}).",
                "affected_ids": [a.id],
                "details": {
                    "assignment_id": a.id,
                    "timeslot_id": a.timeslot_id,
                    "subject_id": a.subject_id
                }
            })

    # 4. Load Distribution Reconciliation (Deduplicated per Entry)
    for entry in load_entries:
        matched_faculty = None
        for f in faculties:
            if match_faculty_names(entry.faculty_name, f.full_name, f.known_initials):
                matched_faculty = f
                break
                
        if not matched_faculty:
            conflicts.append({
                "type": "load_mismatch",
                "severity": "warning",
                "message": f"Load entry '{entry.faculty_name}' teaching '{entry.subject_name}' in section '{entry.section_name}' has no matching Faculty record.",
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
            
        matched_assignments = []
        for a in assignments:
            if a.faculty_id == matched_faculty.id:
                sub = db.query(Subject).filter(Subject.id == a.subject_id).first()
                sub_code = entry.semester.strip() if entry.semester else ""
                
                sub_match = False
                if sub:
                    if sub.code.lower() in sub_code.lower() or sub_code.lower() in sub.code.lower():
                        sub_match = True
                    elif clean_name(sub.name) in clean_name(entry.subject_name) or clean_name(entry.subject_name) in clean_name(sub.name):
                        sub_match = True
                        
                sec_match = False
                p_sec = assignment_parent_sections.get(a.id)
                if p_sec:
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
                "message": f"Load entry '{entry.faculty_name}' -> '{entry.subject_name}' ({entry.section_name}) has no scheduled assignments in the active timetable.",
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
