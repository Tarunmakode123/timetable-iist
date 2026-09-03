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
    "DS_3":   {"id": "DS_3",   "name": "DS (3rd Yr)",   "year": 3, "dept": "DS"},

    # Year 4 (Semesters 7 & 8)
    "CS-1_4": {"id": "CS-1_4", "name": "CS-1 (4th Yr)", "year": 4, "dept": "CSE"},
    "CS-2_4": {"id": "CS-2_4", "name": "CS-2 (4th Yr)", "year": 4, "dept": "CSE"},
    "CS-3_4": {"id": "CS-3_4", "name": "CS-3 (4th Yr)", "year": 4, "dept": "CSE"},
    "IT_4":   {"id": "IT_4",   "name": "IT (4th Yr)",   "year": 4, "dept": "IT"},
    "AIML_4": {"id": "AIML_4", "name": "AIML (4th Yr)", "year": 4, "dept": "AIML"},
    "IoT_4":  {"id": "IoT_4",  "name": "IoT (4th Yr)",  "year": 4, "dept": "IoT"},
    "DS_4":   {"id": "DS_4",   "name": "DS (4th Yr)",   "year": 4, "dept": "DS"},
    "ME_4":   {"id": "ME_4",   "name": "ME (4th Yr)",   "year": 4, "dept": "ME"},
}

RAW_VARIANT_MAP = {
    "cs-1": "CS-1", "cse-1": "CS-1", "cs1": "CS-1", "cse1": "CS-1", "cs 1": "CS-1", "cse 1": "CS-1", "cs_1": "CS-1",
    "cs-2": "CS-2", "cse-2": "CS-2", "cs2": "CS-2", "cse2": "CS-2", "cs 2": "CS-2", "cse 2": "CS-2", "cs_2": "CS-2",
    "cs-3": "CS-3", "cse-3": "CS-3", "cs3": "CS-3", "cse3": "CS-3", "cs 3": "CS-3", "cse 3": "CS-3", "cs_3": "CS-3",
    "iot": "IoT", "internet of things": "IoT", "iot-1": "IoT", "iot_1": "IoT",
    "it": "IT", "it-1": "IT", "information technology": "IT",
    "ds": "DS", "data science": "DS", "ds-1": "DS",
    "aiml": "AIML", "ai-ml": "AIML", "ai&ml": "AIML",
    "mech.": "ME", "mech": "ME", "mechanical": "ME", "me": "ME"
}

def determine_year_from_semester(semester_str: Optional[str]) -> int:
    if not semester_str:
        return 2
    s = str(semester_str).lower().strip()
    
    if any(k in s for k in ["7th", "8th", "vii", "viii", "4th year", "iv year", "bt205"]) or re.search(r'\b(7\d\d|8\d\d)\b', s):
        return 4
    if any(k in s for k in ["5th", "6th", "3rd year", "iii year", "3rd yr"]) or re.search(r'\b(5\d\d|6\d\d)\b', s):
        return 3
    if any(k in s for k in ["3rd", "4th", "2nd year", "ii year", "2nd yr"]) or re.search(r'\b(3\d\d|4\d\d)\b', s):
        return 2
    return 2

def normalize_single_section_name(raw_name: str, year: int = 2) -> Optional[str]:
    if not raw_name:
        return None
    raw_clean = raw_name.strip().lower()
    
    if "mech" in raw_clean or "me" == raw_clean:
        target = f"ME_{year}"
        return target if target in CANONICAL_SECTIONS else "ME_4"

    if raw_clean in ["cs", "cse"]:
        target = f"CS-1_{year}"
        return target if target in CANONICAL_SECTIONS else "CS-1_2"

    if "iot" in raw_clean:
        target = f"IoT_{year}"
        return target if target in CANONICAL_SECTIONS else "IoT_2"

    if "aiml" in raw_clean or "ai-ml" in raw_clean or "ai&ml" in raw_clean:
        target = f"AIML_{year}"
        return target if target in CANONICAL_SECTIONS else "AIML_2"

    if "it" in raw_clean and "iot" not in raw_clean and "unit" not in raw_clean:
        target = f"IT_{year}"
        return target if target in CANONICAL_SECTIONS else "IT_2"

    if "ds" in raw_clean or "data science" in raw_clean:
        target = f"DS_{year}"
        return target if target in CANONICAL_SECTIONS else "DS_2"

    if "cs-3" in raw_clean or "cse-3" in raw_clean or "cs 3" in raw_clean or "cs3" in raw_clean:
        target = f"CS-3_{year}"
        return target if target in CANONICAL_SECTIONS else "CS-3_2"
    if "cs-2" in raw_clean or "cse-2" in raw_clean or "cs 2" in raw_clean or "cs2" in raw_clean:
        target = f"CS-2_{year}"
        return target if target in CANONICAL_SECTIONS else "CS-2_2"
    if "cs-1" in raw_clean or "cse-1" in raw_clean or "cs 1" in raw_clean or "cs1" in raw_clean:
        target = f"CS-1_{year}"
        return target if target in CANONICAL_SECTIONS else "CS-1_2"

    return "CS-1_2"

def normalize_section_entry(raw_section_name: str, semester_raw: Optional[str] = None) -> List[str]:

    if not raw_section_name:
        return []

    year = determine_year_from_semester(semester_raw)
    raw_str = raw_section_name.strip()
    
    if any(delim in raw_str for delim in ["&", " and ", ",", "/"]):
        parts = re.split(r'&|\band\b|,|/', raw_str, flags=re.IGNORECASE)
        canonical_ids = []
        for p in parts:
            p_clean = p.strip()
            if p_clean:
                cid = normalize_single_section_name(p_clean, year)
                if cid and cid != "ambiguous_unassigned" and cid not in canonical_ids:
                    canonical_ids.append(cid)
        return canonical_ids
    else:
        cid = normalize_single_section_name(raw_str, year)
        return [cid] if cid and cid != "ambiguous_unassigned" else []

def calculate_workload_hours(records: List[Dict]) -> float:
    seen_combined = set()
    total_hours = 0.0
    
    for r in records:
        sec_name = str(r.get("section_name") or "").strip().lower()
        sub_name = str(r.get("subject_name") or "").strip().lower()
        th = float(r.get("theory_hours") or 0.0)
        pr = float(r.get("practical_hours") or 0.0)
        tot = th + pr
        
        if any(d in sec_name for d in ["&", " and ", ",", "/"]):
            key = (sub_name, th, pr)
            if key in seen_combined:
                continue
            seen_combined.add(key)
            
        total_hours += tot
        
    return total_hours
