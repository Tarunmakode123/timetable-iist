import sqlite3
import os
import sys
sys.path.insert(0, '.')
from backend.database import DB_PATH, SessionLocal, SystemSetting, set_active_dataset_id, Faculty, Section, Subject, Room, Assignment, LoadDistribution

def run_migration():
    print(f"Running database schema migration on: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Create system_settings table if not exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Add dataset_id and dataset_source columns to tables if missing
    tables = ["faculty", "subjects", "sections", "batches", "rooms", "assignments", "load_distribution"]
    for tbl in tables:
        cursor.execute(f"PRAGMA table_info({tbl})")
        cols = [info[1] for info in cursor.fetchall()]
        if "dataset_id" not in cols:
            print(f"Adding dataset_id to {tbl}")
            cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN dataset_id TEXT DEFAULT 'legacy_seed_2024'")
        if "dataset_source" not in cols:
            print(f"Adding dataset_source to {tbl}")
            cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN dataset_source TEXT DEFAULT 'legacy_seed'")
            
    conn.commit()
    conn.close()
    
    # 3. Backfill active dataset vs legacy seed dataset
    db = SessionLocal()
    try:
        active_id = "ds_active_current_2024"
        legacy_id = "legacy_seed_2024"
        
        set_active_dataset_id(db, active_id, "user_upload")
        
        # All current 115 load_distribution rows belong to current user upload
        db.query(LoadDistribution).update(
            {LoadDistribution.dataset_id: active_id, LoadDistribution.dataset_source: "user_upload"},
            synchronize_session=False
        )
        
        # Get active faculty names in current load distribution
        ld_fac_names = [r[0] for r in db.query(LoadDistribution.faculty_name).distinct().all() if r[0]]
        
        # Update matching faculty records to active dataset
        for fac in db.query(Faculty).all():
            if any(f_name.lower() in fac.full_name.lower() or fac.full_name.lower() in f_name.lower() for f_name in ld_fac_names):
                fac.dataset_id = active_id
                fac.dataset_source = "user_upload"
            else:
                fac.dataset_id = legacy_id
                fac.dataset_source = "legacy_seed"
                
        # Update sections to active dataset
        for sec in db.query(Section).all():
            sec.dataset_id = active_id
            sec.dataset_source = "user_upload"
            
        # Update subjects and rooms to active dataset
        for sub in db.query(Subject).all():
            sub.dataset_id = active_id
            sub.dataset_source = "user_upload"
            
        for rm in db.query(Room).all():
            rm.dataset_id = active_id
            rm.dataset_source = "user_upload"
            
        for asgn in db.query(Assignment).all():
            asgn.dataset_id = active_id
            asgn.dataset_source = "user_upload"
            
        db.commit()
        print("Data backfill migration completed successfully!")
    except Exception as e:
        db.rollback()
        print(f"Migration error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
