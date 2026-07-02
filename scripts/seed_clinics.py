import os
import sys

# Add the project root to sys.path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.storage.database import engine, Base, SessionLocal
from app.storage.sql_models import Clinic

PUNE_CLINICS = [
    {"id": "pune_clinic_1", "name": "Smile Care Dental Clinic Pune"},
    {"id": "pune_clinic_2", "name": "Tooth Corner Kharadi"},
    {"id": "pune_clinic_3", "name": "Pune Dental Studio"},
    {"id": "pune_clinic_4", "name": "Advanced Dental Care Baner"},
    {"id": "pune_clinic_5", "name": "Koregaon Park Dental Spa"},
    {"id": "pune_clinic_6", "name": "Viman Nagar Orthodontics"},
]

def seed():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")
    
    print("Seeding clinics...")
    db = SessionLocal()
    try:
        for clinic_data in PUNE_CLINICS:
            existing = db.query(Clinic).filter(Clinic.id == clinic_data["id"]).first()
            if not existing:
                print(f"Adding clinic: {clinic_data['name']}")
                clinic = Clinic(id=clinic_data["id"], name=clinic_data["name"])
                db.add(clinic)
            else:
                print(f"Clinic {clinic_data['name']} already exists.")
        
        # Add default_clinic if needed by tests/codebase
        if not db.query(Clinic).filter(Clinic.id == "default_clinic").first():
            db.add(Clinic(id="default_clinic", name="Default Clinic"))

        db.commit()
        print("Seeding completed.")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
