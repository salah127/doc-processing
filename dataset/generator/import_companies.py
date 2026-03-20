import csv
import os
import random
from pymongo import MongoClient
from faker import Faker

# Configuration
CSV_PATH = "dataset/StockUniteLegale_utf8.csv"
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/hackathon")
DB_NAME = "hackathon"
COLLECTION_NAME = "companies"

fake = Faker("fr_FR")

def import_20_companies():
    print(f"Reading {CSV_PATH}...")
    
    companies = []
    count = 0
    target_count = 20

    if not os.path.exists(CSV_PATH):
        print(f"Error: {CSV_PATH} not found.")
        return

    try:
        # Use UTF-8 and ignore errors if any weird characters appear
        with open(CSV_PATH, mode='r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Filter for active companies if possible
                # In SIRENE: etatAdministratifUniteLegale 'A' = Active
                etat = row.get('etatAdministratifUniteLegale', 'A') 
                
                # We want companies with a name
                name = row.get('denominationUniteLegale')
                if not name:
                    # Try person name
                    nom = row.get('nomUniteLegale', '')
                    prenom = row.get('prenomUniteLegale', '')
                    if nom:
                        name = f"{nom} {prenom}".strip()
                
                if etat == 'A' and name:
                    companies.append({
                        "siren": row.get('siren'),
                        "siret": row.get('siren') + str(random.randint(10000, 99999)), # SIRET = SIREN + 5 digits NIC
                        "name": name,
                        "address": fake.address().replace("\n", ", "),
                        "sigle": row.get('sigleUniteLegale'),
                        "date_creation": row.get('dateCreationUniteLegale'),
                        "categorie": row.get('categorieJuridiqueUniteLegale'),
                        "activite": row.get('activitePrincipaleUniteLegale'),
                        "etat": etat
                    })
                    count += 1
                    if count % 5 == 0:
                        print(f"Found {count} companies...")
                
                if count >= target_count:
                    break

        if not companies:
            print("No companies found matching criteria.")
            return

        print(f"Connecting to MongoDB at {MONGO_URI}...")
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        coll = db[COLLECTION_NAME]
        
        # Clear existing and insert
        coll.delete_many({})
        result = coll.insert_many(companies)
        
        print(f"Successfully inserted {len(result.inserted_ids)} companies into MongoDB.")
        
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    import_20_companies()
