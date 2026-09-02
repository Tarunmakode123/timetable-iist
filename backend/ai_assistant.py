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
            
        # 2. Clean ID match
        if clean_id and len(clean_id) >= 3 and clean_id in prompt_clean:
            score += 120
            
        # 3. Individual token matches (e.g. shweta, agrawal, rakesh, verma)
        name_tokens = [t for t in clean_full_name.split() if len(t) >= 3 and t not in ['dr', 'mr', 'ms', 'mrs', 'prof']]
        matched_tokens = [t for t in name_tokens if t in prompt_words or t in prompt_clean]
        score += len(matched_tokens) * 40
        
        if score > best_score and score >= 30:
            best_score = score
            best_faculty = f
            
    return best_faculty

def find_best_section_match(prompt: str, sections: list):
    prompt_clean = prompt.lower().replace(" ", "").replace("-", "").replace("_", "")
    for s in sections:
        clean_id = s.id.lower().replace(" ", "").replace("-", "").replace("_", "")
        clean_name = s.name.lower().replace(" ", "").replace("-", "").replace("_", "")
        if clean_id in prompt_clean or clean_name in prompt_clean:
            return s
        # Fuzzy shorthand like cs1 -> cs-1_2
        if "cs1" in prompt_clean and "cs-1" in s.name.lower():
            return s
        if "iot" in prompt_clean and "iot" in s.name.lower():
            return s
        if "aiml" in prompt_clean and "aiml" in s.name.lower():
            return s
    return None

ACTION_KEYWORDS = ["move", "shift", "change", "cancel", "delete", "add", "swap", "edit", "put", "set", "assign", "place", "insert", "relocate", "transfer", "allocate", "reschedule", "replace", "fix", "update", "arrange"]

def process_ai_request(prompt: str, db: Session) -> Dict[str, Any]:
    prompt_lower = prompt.lower().strip()

    # 1. Broad Action Detection: Verb matched OR explicit mutation request (day + period + entity)
    is_action = any(a in prompt_lower for a in ACTION_KEYWORDS)
    days_map = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    found_days = [d.capitalize() for d in days_map if d in prompt_lower]
    periods = re.findall(r'\b(?:period|p)\s*([1-8])\b', prompt_lower) or re.findall(r'\b([1-8])\b', prompt_lower)
    
    if not is_action and found_days and periods and any(k in prompt_lower for k in ["dbms", "python", "lab", "eees", "al304", "cs501", "shweta", "rakesh", "reshu", "richa"]):
        is_action = True

    if is_action:
        return handle_action_intent(prompt_lower, db)

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

    if matched_room:
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
            "text": f"Room '{matched_room.name}' has {len(room_assigns)} scheduled class(es)" + (f" on {target_day}" if target_day else "") + ":\n" + "\n".join(details),
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
    matched_section = find_best_section_match(prompt, sections)

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
                summary_text += f"\n• {ts_label}: {sub.name if sub else a.subject_id} by {fac.full_name if fac else a.faculty_id} in {a.room_id}"

        return {
            "mode": "query",
            "target_type": "section",
            "target_id": matched_section.id,
            "text": summary_text,
            "data": []
        }

    # 4. Check for Subject Query (e.g. "who teaches AL304?")
    matched_sub = None
    for sb in subjects:
        if sb.code.lower() in prompt or sb.name.lower() in prompt:
            matched_sub = sb
            break
            
    if matched_sub:
        sub_assigns = [a for a in assignments if a.subject_id == matched_sub.id]
        if sub_assigns:
            summary_text = f"Subject '{matched_sub.name}' ({matched_sub.code}) Scheduling Details:"
            for a in sub_assigns[:10]:
                fac = next((fc for fc in faculties if fc.id == a.faculty_id), None)
                sec = next((sc for sc in sections if sc.id == a.section_id), None)
                summary_text += f"\n• {format_timeslot_label(a.timeslot_id)}: Taught by {fac.full_name if fac else a.faculty_id} for Section {sec.name if sec else a.section_id} in {a.room_id}"
            return {
                "mode": "query",
                "text": summary_text,
                "data": []
            }

    # General overview fallback guidance
    return {
        "mode": "query",
        "text": f"I am your IIST Timetable Assistant! Currently tracking {len(assignments)} assignments across {len(faculties)} faculty members, {len(sections)} sections, and {len(rooms)} rooms.\n\nYou can ask for any schedule (e.g. 'show Dr. Shweta Agrawal schedule' or 'is LAB1 free on Monday') or request any timetable edit (e.g. 'put DBMS on Wednesday P1 for Shweta Agrawal').",
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
    periods = re.findall(r'\b(?:period|p)\s*([1-8])\b', prompt.lower())
    if not periods:
        periods = re.findall(r'\b([1-8])\b', prompt.lower())

    # Match faculty or section mentioned
    target_fac = find_best_faculty_match(prompt, faculties)
    target_sec = find_best_section_match(prompt, sections)

    # Action 1: Cancel / Delete class
    if any(k in prompt for k in ["cancel", "delete", "remove", "drop"]):
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
    if any(k in prompt for k in ["move", "shift", "change", "put", "edit", "set", "assign", "place", "insert", "relocate", "transfer", "allocate", "reschedule", "replace", "fix", "update", "arrange"]):
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
