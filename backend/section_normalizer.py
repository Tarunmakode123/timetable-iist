import re
from typing import List, Dict, Tuple, Optional

# Canonical Section Registry
# Year 2 Sections (3rd & 4th Semesters)
# Year 3 Sections (5th & 6th Semesters)

CANONICAL_SECTIONS = {
    # Year 2 (Semesters 3 & 4)
    "CS-1_2": {"id": "CS-1_2", "name": "CS-1", "year": 2, "dept": "CSE"},
    "CS-2_2": {"id": "CS-2_2", "name": "CS-2", "year": 2, "dept": "CSE"},
    "CS-3_2": {"id": "CS-3_2", "name": "CS-3", "year": 2, "dept": "CSE"},
    "IT_2":   {"id": "IT_2",   "name": "IT",   "year": 2, "dept": "IT"},
    "AIML_2": {"id": "AIML_2", "name": "AIML", "year": 2, "dept": "AIML"},
    "DS_2":   {"id": "DS_2",   "name": "DS",   "year": 2, "dept": "DS"},
    "IoT_2":  {"id": "IoT_2",  "name": "IoT",  "year": 2, "dept": "IoT"},

    # Year 3 (Semesters 5 & 6)
    "CS-1_3": {"id": "CS-1_3", "name": "CS-1 (3rd Yr)", "year": 3, "dept": "CSE"},
    "CS-2_3": {"id": "CS-2_3", "name": "CS-2 (3rd Yr)", "year": 3, "dept": "CSE"},
    "CS-3_3": {"id": "CS-3_3", "name": "CS-3 (3rd Yr)", "year": 3, "dept": "CSE"},
    "IT_3":   {"id": "IT_3",   "name": "IT (3rd Yr)",   "year": 3, "dept": "IT"},
    "AIML_3": {"id": "AIML_3", "name": "AIML (3rd Yr)", "year": 3, "dept": "AIML"},
    "IoT_3":  {"id": "IoT_3",  "name": "IoT (3rd Yr)",  "year": 3, "dept": "IoT"},
}

RAW_VARIANT_MAP = {
    # CS-1 variants
    "cs-1": "CS-1", "cse-1": "CS-1", "cs1": "CS-1", "cse1": "CS-1", "cs 1": "CS-1", "cse 1": "CS-1", "cs_1": "CS-1",
    # CS-2 variants
    "cs-2": "CS-2", "cse-2": "CS-2", "cs2": "CS-2", "cse2": "CS-2", "cs 2": "CS-2", "cse 2": "CS-2", "cs_2": "CS-2",
    # CS-3 variants
    "cs-3": "CS-3", "cse-3": "CS-3", "cs3": "CS-3", "cse3": "CS-3", "cs 3": "CS-3", "cse 3": "CS-3", "cs_3": "CS-3",
    # IoT variants
    "iot": "IoT", "internet of things": "IoT", "iot-1": "IoT", "iot_1": "IoT",
    # IT variants
    "it": "IT", "it-1": "IT", "information technology": "IT",
    # DS variants
    "ds": "DS", "data science": "DS", "ds-1": "DS",
    # AIML variants
    "aiml": "AIML", "ai-ml": "AIML", "ai&ml": "AIML",
    # Mechanical variants
    "mech.": "ME", "mech": "ME", "mechanical": "ME", "me": "ME"
}

def determine_year_from_semester(semester_str: Optional[str]) -> int:
    if not semester_str:
        return 2
    s_lower = str(semester_str).lower().strip()
    if any(k in s_lower for k in ["v", "vi", "5th", "6th", "iii year", "3rd year", "3rd yr"]):
        return 3
    if any(k in s_lower for k in ["vii", "viii", "7th", "8th", "iv year", "4th year"]):
        return 4
    return 2

def normalize_single_section_name(raw_name: str, year: int = 2) -> Optional[str]:
    if not raw_name:
        return None
    raw_clean = raw_name.strip().lower()
    
    # Direct check in RAW_VARIANT_MAP
    base_name = RAW_VARIANT_MAP.get(raw_clean)
    if not base_name:
        # Strip trailing year descriptors
        cleaned = re.sub(r'\b(2nd|3rd|4th|ii|iii|iv)\s*(year|yr)?\b', '', raw_clean).strip()
        base_name = RAW_VARIANT_MAP.get(cleaned)
        
    if not base_name:
        # Fallback keyword checks
        if "aiml" in raw_clean: base_name = "AIML"
        elif "iot" in raw_clean: base_name = "IoT"
        elif "it" in raw_clean: base_name = "IT"
        elif "ds" in raw_clean or "data science" in raw_clean: base_name = "DS"
        elif "cs-3" in raw_clean or "cse-3" in raw_clean or "cs 3" in raw_clean or "cs3" in raw_clean: base_name = "CS-3"
        elif "cs-2" in raw_clean or "cse-2" in raw_clean or "cs 2" in raw_clean or "cs2" in raw_clean: base_name = "CS-2"
        elif "cs-1" in raw_clean or "cse-1" in raw_clean or "cs 1" in raw_clean or "cs1" in raw_clean or "cs" in raw_clean: base_name = "CS-1"
        elif "mech" in raw_clean or "me" in raw_clean: base_name = "ME"

    if not base_name:
        return None

    sec_id = f"{base_name}_{year}"
    if sec_id in CANONICAL_SECTIONS:
        return sec_id
    
    # Fallback to year 2 if year 3 doesn't exist for DS/ME
    sec_id_2 = f"{base_name}_2"
    if sec_id_2 in CANONICAL_SECTIONS:
        return sec_id_2
        
    return None

def normalize_section_entry(raw_section_name: str, semester_raw: Optional[str] = None) -> List[str]:

    if not raw_section_name:
        return []

    year = determine_year_from_semester(semester_raw)
    raw_str = raw_section_name.strip()
    
    # Check for combined section delimiters (&, and, comma, slash)
    if any(delim in raw_str for delim in ["&", " and ", ",", "/"]):
        parts = re.split(r'&|\band\b|,|/', raw_str, flags=re.IGNORECASE)
        canonical_ids = []
        for p in parts:
            p_clean = p.strip()
            if p_clean:
                cid = normalize_single_section_name(p_clean, year)
                if cid and cid not in canonical_ids:
                    canonical_ids.append(cid)
        return canonical_ids
    else:
        cid = normalize_single_section_name(raw_str, year)
        return [cid] if cid else []

def calculate_workload_hours(records: List[Dict]) -> float:

    seen_sessions = set()
    total_hours = 0.0
    
    for r in records:
        fac_name = r.get("faculty_name", "").strip().lower()
        sub_name = r.get("subject_name", "").strip().lower()
        th = float(r.get("theory_hours") or 0.0)
        pr = float(r.get("practical_hours") or 0.0)
        tot = float(r.get("total_hours") or (th + pr))
        
        # Deduplication key for shared/combined section entries
        session_key = (fac_name, sub_name, th, pr)
        if session_key in seen_sessions:
            continue
        seen_sessions.add(session_key)
        total_hours += tot
        
    return total_hours
