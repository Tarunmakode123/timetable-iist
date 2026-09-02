import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.database import Faculty, Subject, Section, Batch, Room, TimeSlot, Assignment
from backend.validator import validate_all

TIMESLOT_LABEL_MAP = {
    "1": "P1 (09:30 - 10:20 AM)",
    "2": "P2 (10:20 - 11:10 AM)",
    "3": "P3 (11:10 AM - 12:00 PM)",
    "4": "P4 (12:00 - 12:50 PM)",
    "5": "Lunch (12:50 - 01:40 PM)",
    "6": "P5 (01:40 - 02:30 PM)",
    "7": "P6 (02:30 - 03:20 PM)",
    "8": "P7 (03:20 - 04:10 PM)"
}

def format_timeslot_label(ts_id: str) -> str:
    if not ts_id or "_" not in ts_id:
        return ts_id or ""
    parts = ts_id.split("_")
    day = parts[0]
    period_num = parts[1]
    time_label = TIMESLOT_LABEL_MAP.get(period_num, f"Period {period_num}")
    return f"{day}, {time_label}"

def format_clean_name(name: str) -> str:
    if not name:
        return ""
    return name.replace("_", " ").title()

def find_best_faculty_match(prompt: str, faculties: list):
    prompt_clean = prompt.lower()
    prompt_words = set(re.findall(r'\w+', prompt_clean))
    
    best_faculty = None
    best_score = 0
    
    for f in faculties:
        score = 0
        full_name = f.full_name or ""
        clean_full_name = re.sub(r'^(dr|mr|ms|mrs|prof)\.?\s*', '', full_name.lower()).strip()
        clean_id = f.id.replace("_", " ").lower().strip()
        
        # 1. Exact full name match (without Dr/Mr/Ms prefix)
        if clean_full_name and len(clean_full_name) >= 3 and clean_full_name in prompt_clean:
            score += 150
            
        # 2. Clean ID match (e.g. shweta agrawal in prompt)
        if clean_id and len(clean_id) >= 3 and clean_id in prompt_clean:
            score += 120
            
        # 3. Word overlap score
        f_name_words = set(re.findall(r'\w+', clean_full_name))
        ignored = {"dr", "mr", "ms", "mrs", "prof", "schedule", "of", "the", "for", "give", "me", "full", "show", "list", "timetable", "class", "classes"}
        matching_words = (prompt_words & f_name_words) - ignored
        score += len(matching_words) * 30
        
        # 4. Exact word match for initials (only if initials length >= 2)
        if f.known_initials and len(f.known_initials.strip()) >= 2:
            init_pattern = r'\b' + re.escape(f.known_initials.strip().lower()) + r'\b'
            if re.search(init_pattern, prompt_clean):
                score += 50
                
        if score > best_score and score >= 30:
            best_score = score
            best_faculty = f
            
    return best_faculty

ACTION_KEYWORDS = ["move", "shift", "change", "cancel", "delete", "add", "swap", "edit", "put", "set", "assign", "place", "insert"]

def process_ai_request(prompt: str, db: Session) -> Dict[str, Any]:
    prompt_lower = prompt.lower().strip()

    # 1. QUERY MODE (READ-ONLY)
    if re.search(r'\b(what|show|list|schedule|who|where|how\s+many|is|are|can|check|give)\b', prompt_lower):
        if not any(a in prompt_lower for a in ACTION_KEYWORDS):
            return handle_query_intent(prompt_lower, db)

    # 2. ACTION MODE (MUTATIONS & EDITS)
    if any(a in prompt_lower for a in ACTION_KEYWORDS):
        return handle_action_intent(prompt_lower, db)

    # Fallback search as query mode
    return handle_query_intent(prompt_lower, db)

def handle_query_intent(prompt: str, db: Session) -> Dict[str, Any]:
    faculties = db.query(Faculty).all()
    sections = db.query(Section).all()
    rooms = db.query(Room).all()
    assignments = db.query(Assignment).all()
    subjects = db.query(Subject).all()

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    target_day = None
    for d in days:
        if d in prompt:
            target_day = d.capitalize()
            break

    # 1. Check for room availability / occupancy query
    matched_room = None
    for r in rooms:
        r_clean = r.id.replace("_", "").lower()
        r_name_clean = r.name.replace("_", "").lower()
        prompt_clean = prompt.replace(" ", "").replace("_", "").lower()
        if r_clean in prompt_clean or r_name_clean in prompt_clean:
            matched_room = r
            break

    if matched_room and ("free" in prompt or "available" in prompt or "vacant" in prompt):
        room_assigns = [a for a in assignments if a.room_id == matched_room.id]
        if target_day:
            room_assigns = [a for a in room_assigns if a.timeslot_id.startswith(target_day)]

        if not room_assigns:
            return {
                "mode": "query",
                "target_type": "room",
                "target_id": matched_room.id,
                "text": f"Room '{matched_room.name}' ({matched_room.type}) is FREE with no scheduled classes{f' on {target_day}' if target_day else ''}.",
                "data": []
            }
        
        details = []
        for a in room_assigns:
            sub = next((s for s in subjects if s.id == a.subject_id), None)
            sec = next((s for s in sections if s.id == a.section_id), None)
            fac = next((f for f in faculties if f.id == a.faculty_id), None)
            ts_label = format_timeslot_label(a.timeslot_id)
            details.append(f"• {ts_label}: {sub.name if sub else a.subject_id} ({sec.name if sec else a.section_id or 'General'}) taught by {fac.full_name if fac else a.faculty_id}")

        return {
            "mode": "query",
            "target_type": "room",
            "target_id": matched_room.id,
            "text": f"Room '{matched_room.name}' has {len(room_assigns)} scheduled class(es){f' on {target_day}' if target_day else ''}:\n" + "\n".join(details),
            "data": []
        }

    # 2. Check for faculty schedule query
    matched_faculty = find_best_faculty_match(prompt, faculties)

    if matched_faculty:
        fac_assigns = [a for a in assignments if a.faculty_id == matched_faculty.id]
        if target_day:
            fac_assigns = [a for a in fac_assigns if a.timeslot_id.startswith(target_day)]

        if not fac_assigns:
            return {
                "mode": "query",
                "target_type": "faculty",
                "target_id": matched_faculty.id,
                "text": f"Faculty '{matched_faculty.full_name}' has no scheduled classes{f' on {target_day}' if target_day else ''}.",
                "data": []
            }

        details = []
        for a in fac_assigns:
            sub = next((s for s in subjects if s.id == a.subject_id), None)
            sec = next((s for s in sections if s.id == a.section_id), None)
            rm = next((r for r in rooms if r.id == a.room_id), None)
            details.append({
                "timeslot_id": a.timeslot_id,
                "timeslot": format_timeslot_label(a.timeslot_id),
                "subject": sub.name if sub else format_clean_name(a.subject_id),
                "section": sec.name if sec else format_clean_name(a.section_id),
                "room": rm.name if rm else format_clean_name(a.room_id),
                "batch": a.batch_id.split("_").pop() if a.batch_id else ""
            })

        summary_text = f"Full Weekly Schedule for '{matched_faculty.full_name}' ({len(details)} class(es)){f' on {target_day}' if target_day else ''}:"
        for d in details:
            batch_str = f" [Batch {d['batch']}]" if d['batch'] else ""
            summary_text += f"\n• {d['timeslot']}: {d['subject']}{batch_str} in {d['room']} ({d['section'] or 'General Section'})"

        return {
            "mode": "query",
            "target_type": "faculty",
            "target_id": matched_faculty.id,
            "text": summary_text,
            "data": details
        }

    # 3. Check for section schedule query
    matched_section = None
    for s in sections:
        clean_s = s.id.replace("_", "").replace("-", "").lower()
        if clean_s in prompt.replace(" ", "").replace("-", ""):
            matched_section = s
            break

    if matched_section:
        sec_assigns = [a for a in assignments if a.section_id == matched_section.id]
        if target_day:
            sec_assigns = [a for a in sec_assigns if a.timeslot_id.startswith(target_day)]

        summary_text = f"Schedule for Section '{matched_section.name}'{f' on {target_day}' if target_day else ''}:"
        if not sec_assigns:
            summary_text += " No scheduled classes."
        else:
            for a in sec_assigns:
                sub = next((sb for sb in subjects if sb.id == a.subject_id), None)
                fac = next((fc for fc in faculties if fc.id == a.faculty_id), None)
                ts_label = format_timeslot_label(a.timeslot_id)
                summary_text += f"\n• {ts_label}: {sub.code if sub else a.subject_id} by {fac.full_name if fac else a.faculty_id} in {a.room_id}"

        return {
            "mode": "query",
            "target_type": "section",
            "target_id": matched_section.id,
            "text": summary_text,
            "data": []
        }

    # General overview response
    return {
        "mode": "query",
        "text": f"The dataset currently has {len(assignments)} assignments across {len(faculties)} faculty members, {len(sections)} sections, and {len(rooms)} rooms.",
        "data": []
    }

def handle_action_intent(prompt: str, db: Session) -> Dict[str, Any]:
    faculties = db.query(Faculty).all()
    sections = db.query(Section).all()
    assignments = db.query(Assignment).all()
    rooms = db.query(Room).all()
    timeslots = db.query(TimeSlot).all()

    # Extract days and period numbers from prompt
    days_map = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    found_days = [d.capitalize() for d in days_map if d in prompt.lower()]
    periods = re.findall(r'\b(?:period|p)\s*([1-8])\b', prompt, re.IGNORECASE)
    if not periods:
        periods = re.findall(r'\b([1-8])\b', prompt)

    # Match faculty or section mentioned
    target_fac = find_best_faculty_match(prompt, faculties)

    target_sec = None
    for s in sections:
        clean_s = s.id.replace("_", "").replace("-", "").lower()
        if clean_s in prompt.replace(" ", "").replace("-", ""):
            target_sec = s
            break

    # Action 1: Cancel / Delete class
    if "cancel" in prompt or "delete" in prompt:
        matching = [a for a in assignments if (target_fac and a.faculty_id == target_fac.id) or (target_sec and a.section_id == target_sec.id)]
        if found_days and periods:
            target_ts = f"{found_days[0]}_{periods[0]}"
            matching = [a for a in matching if a.timeslot_id == target_ts]

        if not matching:
            return {
                "mode": "action",
                "status": "error",
                "text": "Could not find a matching class assignment to cancel based on your prompt.",
                "diff": None
            }

        target = matching[0]
        return {
            "mode": "action",
            "status": "valid",
            "text": f"Proposed Cancellation: Remove class [{target.timeslot_id}] for {target.faculty_id} in {target.room_id}.",
            "diff": {
                "to_delete": [target.id],
                "to_add": [],
                "description": f"Cancel assignment #{target.id} ({target.timeslot_id})"
            }
        }

    # Action 2: Move / Shift / Edit / Put / Set / Assign class
    if any(k in prompt for k in ["move", "shift", "change", "put", "edit", "set", "assign", "place", "insert"]):
        # Advanced regex extraction for explicit "from ... to ..."
        to_slot_match = re.search(r'\bto\s+([a-zA-Z]+)?(?:\s*(?:period|p)\s*|\s*[_]?)([1-8])\b', prompt, re.IGNORECASE)
        from_slot_match = re.search(r'\bfrom\s+([a-zA-Z]+)?(?:\s*(?:period|p)\s*|\s*[_]?)([1-8])\b', prompt, re.IGNORECASE)
        
        # Check for subject name in prompt
        matched_sub = None
        for sb in db.query(Subject).all():
            if sb.name.lower() in prompt or sb.code.lower() in prompt:
                matched_sub = sb
                break
                
        matching = [a for a in assignments if (target_fac and a.faculty_id == target_fac.id) or (target_sec and (a.section_id == target_sec.id or (a.batch_id and target_sec.id in a.batch_id)))]
        if matched_sub:
            sub_matches = [a for a in matching if a.subject_id == matched_sub.id]
            if sub_matches:
                matching = sub_matches
                
        if from_slot_match:
            from_day = from_slot_match.group(1).capitalize() if from_slot_match.group(1) else (found_days[0] if found_days else "Monday")
            from_period = from_slot_match.group(2)
            from_ts = f"{from_day}_{from_period}"
            from_matches = [a for a in matching if a.timeslot_id == from_ts]
            if from_matches:
                source_assign = from_matches[0]
            else:
                source_assign = matching[0] if matching else None
        else:
            source_assign = matching[0] if matching else (assignments[0] if assignments else None)

        if not source_assign:
            return {"mode": "action", "status": "error", "text": "No matching assignment found to move.", "diff": None}

        # Target slot determination
        if to_slot_match:
            to_day = to_slot_match.group(1).capitalize() if to_slot_match.group(1) else (found_days[0] if found_days else source_assign.timeslot_id.split("_")[0])
            to_period = to_slot_match.group(2)
            new_ts = f"{to_day}_{to_period}"
        elif len(found_days) >= 2 and len(periods) >= 2:
            new_ts = f"{found_days[1]}_{periods[1]}"
        elif len(found_days) >= 1 and len(periods) >= 1:
            new_ts = f"{found_days[0]}_{periods[0]}"
        else:
            new_ts = "Tuesday_3"

        # Check if target slot is lunch period 5 (12:50 - 13:40)
        if new_ts.endswith("_5"):
            return {
                "mode": "action",
                "status": "conflict",
                "text": f"Cannot move class to [{new_ts}]: Period 5 (12:50 - 13:40) is reserved for the institutional lunch break.",
                "alternatives": [f"{new_ts.split('_')[0]}_4", f"{new_ts.split('_')[0]}_6"],
                "diff": None
            }

        # Construct proposed change
        proposed_assign = {
            "faculty_id": source_assign.faculty_id,
            "subject_id": source_assign.subject_id,
            "section_id": source_assign.section_id,
            "batch_id": source_assign.batch_id,
            "room_id": source_assign.room_id,
            "timeslot_id": new_ts,
            "effective_from": source_assign.effective_from,
            "source": "ai_assistant"
        }

        # Check for potential room or faculty double-booking in target slot
        room_busy = [a for a in assignments if a.id != source_assign.id and a.room_id == source_assign.room_id and a.timeslot_id == new_ts]
        fac_busy = [a for a in assignments if a.id != source_assign.id and a.faculty_id == source_assign.faculty_id and a.timeslot_id == new_ts]

        if room_busy or fac_busy:
            conflict_reason = []
            if room_busy:
                conflict_reason.append(f"Room '{source_assign.room_id}' is already booked by '{room_busy[0].section_id}'")
            if fac_busy:
                conflict_reason.append(f"Faculty '{source_assign.faculty_id}' is already teaching in '{fac_busy[0].room_id}'")

            # Propose 2 safe alternative timeslots
            alternatives = []
            all_ts_ids = [ts.id for ts in timeslots if not ts.id.endswith("_5")]
            for ts_candidate in all_ts_ids:
                if ts_candidate == new_ts:
                    continue
                r_free = not any(a for a in assignments if a.id != source_assign.id and a.room_id == source_assign.room_id and a.timeslot_id == ts_candidate)
                f_free = not any(a for a in assignments if a.id != source_assign.id and a.faculty_id == source_assign.faculty_id and a.timeslot_id == ts_candidate)
                if r_free and f_free:
                    alternatives.append(ts_candidate)
                if len(alternatives) >= 2:
                    break

            return {
                "mode": "action",
                "status": "conflict",
                "text": f"Cannot move class to [{new_ts}]: {', '.join(conflict_reason)}.",
                "alternatives": alternatives,
                "diff": None
            }

        # Safe move
        return {
            "mode": "action",
            "status": "valid",
            "text": f"Proposed Move: Shift {source_assign.subject_id} for {source_assign.faculty_id} from [{source_assign.timeslot_id}] to [{new_ts}].",
            "diff": {
                "to_delete": [source_assign.id],
                "to_add": [proposed_assign],
                "description": f"Move class to {new_ts}"
            }
        }

    return {
        "mode": "action",
        "status": "info",
        "text": f"I parsed your action request '{prompt}'. Please specify the faculty/section and the target day/period.",
        "diff": None
    }
