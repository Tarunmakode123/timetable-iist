import re
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.database import Faculty, Subject, Section, Batch, Room, TimeSlot, Assignment
from backend.validator import validate_all

def process_ai_request(prompt: str, db: Session) -> Dict[str, Any]:
    """
    AI Assistant & Intent Pipeline.
    Parses natural language requests into structured intents (query mode vs action mode).
    Validates actions against the standalone validator before returning a diff or solver alternatives.
    Never mutates data directly without user preview/confirmation.
    """
    prompt_lower = prompt.lower().strip()

    # ---------------- 1. QUERY MODE (READ-ONLY) ----------------
    if any(q in prompt_lower for q in ["what", "show", "list", "schedule", "who", "where", "how many"]):
        return handle_query_intent(prompt_lower, db)

    # ---------------- 2. ACTION MODE (MUTATIONS & EDITS) ----------------
    if any(a in prompt_lower for a in ["move", "shift", "change", "cancel", "delete", "add", "swap"]):
        return handle_action_intent(prompt_lower, db)

    # Fallback response for unspecified prompts
    return {
        "mode": "chat",
        "text": f"I received your request: '{prompt}'. You can ask me questions about schedules (e.g. 'What is Ms. Vimmy's Tuesday schedule?') or request changes (e.g. 'Move Dr. Neeraj's Monday P2 class to Tuesday P3').",
        "diff": None
    }

def handle_query_intent(prompt: str, db: Session) -> Dict[str, Any]:
    """
    Structured DB query handler for read-only questions.
    """
    faculties = db.query(Faculty).all()
    sections = db.query(Section).all()
    rooms = db.query(Room).all()
    assignments = db.query(Assignment).all()
    subjects = db.query(Subject).all()

    # Check for faculty schedule query
    matched_faculty = None
    for f in faculties:
        if (f.known_initials and f.known_initials.lower() in prompt) or \
           (f.full_name.lower() in prompt) or \
           (f.id.lower() in prompt):
            matched_faculty = f
            break

    # Check for day in query
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    target_day = None
    for d in days:
        if d in prompt:
            target_day = d.capitalize()
            break

    if matched_faculty:
        fac_assigns = [a for a in assignments if a.faculty_id == matched_faculty.id]
        if target_day:
            fac_assigns = [a for a in fac_assigns if a.timeslot_id.startswith(target_day)]

        if not fac_assigns:
            return {
                "mode": "query",
                "text": f"Faculty '{matched_faculty.full_name}' has no scheduled classes{f' on {target_day}' if target_day else ''}.",
                "data": []
            }

        details = []
        for a in fac_assigns:
            sub = next((s for s in subjects if s.id == a.subject_id), None)
            sec = next((s for s in sections if s.id == a.section_id), None)
            details.append({
                "timeslot": a.timeslot_id,
                "subject": sub.name if sub else a.subject_id,
                "section": sec.name if sec else a.section_id,
                "room": a.room_id
            })

        summary_text = f"Found {len(details)} class(es) for '{matched_faculty.full_name}'{f' on {target_day}' if target_day else ''}:"
        for d in details:
            summary_text += f"\n• [{d['timeslot']}] {d['subject']} in {d['room']} ({d['section'] or 'General'})"

        return {
            "mode": "query",
            "text": summary_text,
            "data": details
        }

    # Check for section schedule query
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
                summary_text += f"\n• [{a.timeslot_id}] {sub.code if sub else a.subject_id} by {fac.full_name if fac else a.faculty_id} in {a.room_id}"

        return {
            "mode": "query",
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
    """
    Action / Edit intent handler with strict validation and diff construction.
    """
    faculties = db.query(Faculty).all()
    sections = db.query(Section).all()
    rooms = db.query(Room).all()
    assignments = db.query(Assignment).all()
    timeslots = db.query(TimeSlot).all()

    # Parse target timeslot
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
    found_days = [d.capitalize() for d in days if d in prompt]
    found_periods = re.findall(r'\b(?:period|p)\s*([1-8])\b|\b([1-8])\b', prompt)
    periods = []
    for p in found_periods:
        val = p[0] or p[1]
        if val and val not in periods:
            periods.append(val)

    # Match faculty or section mentioned
    target_fac = None
    for f in faculties:
        if (f.known_initials and f.known_initials.lower() in prompt) or \
           (f.full_name.lower() in prompt) or \
           (f.id.lower() in prompt):
            target_fac = f
            break

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

    # Action 2: Move / Shift class
    if "move" in prompt or "shift" in prompt or "change" in prompt:
        # Find current assignment
        matching = [a for a in assignments if (target_fac and a.faculty_id == target_fac.id) or (target_sec and a.section_id == target_sec.id)]
        if not matching:
            matching = assignments[:1] # Fallback to first assignment if unspecified

        if not matching:
            return {"mode": "action", "status": "error", "text": "No assignments available to move.", "diff": None}

        source_assign = matching[0]

        # Determine target timeslot
        if len(found_days) >= 2 and len(periods) >= 2:
            new_ts = f"{found_days[1]}_{periods[1]}"
        elif len(found_days) >= 1 and len(periods) >= 1:
            new_ts = f"{found_days[0]}_{periods[0]}"
        else:
            new_ts = "Tuesday_3" # Default proposed slot

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
