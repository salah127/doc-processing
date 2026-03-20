import os
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for
from pymongo import MongoClient

# --- CONFIG ---
app = Flask(__name__)
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/hackathon")

def get_db():
    client = MongoClient(MONGO_URI)
    return client.hackathon

# --- ROUTES ---

@app.route('/')
@app.route('/home.html')
def home():
    return render_template('home.html')

@app.route('/upload.html')
def upload_page():
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    if 'files' not in request.files:
        return jsonify({"error": "No files provided"}), 400
    
    files = request.files.getlist('files')
    files_payload = []
    
    for f in files:
        files_payload.append(('files', (f.filename, f.read(), f.content_type)))
    
    try:
        resp = requests.post(f"{BACKEND_URL}/upload", files=files_payload)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/mes_documents.html')
def documents():
    db = get_db()
    
    # Filters from query params - handling empty strings correctly
    st_filter = request.args.get('status', '').strip()
    type_filter = request.args.get('type', '').strip()
    siret_filter = request.args.get('siret', '').strip()
    company_filter = request.args.get('company', '').strip()
    
    query = {}
    
    # Specific type filter
    if type_filter:
        query['predicted_type'] = type_filter

    # Advanced Filter: Logic depends on anomalies collection presence
    if st_filter == 'valid' or st_filter == 'error':
        anomalous_doc_ids = db.anomalies.distinct("document_ids")
        if st_filter == 'valid':
            query['document_id'] = {"$nin": anomalous_doc_ids}
            query['status'] = 'curated'
        else: # error
            query['document_id'] = {"$in": anomalous_doc_ids}
        
    # Get all matching documents
    docs = list(db.documents.find(query).sort("uploaded_at", -1))
    
    enriched_docs = []
    for doc in docs:
        doc_id = doc['document_id']
        ext_data = db.extracted_data.find_one({"document_id": doc_id}) or {}
        val_data = db.validated_records.find_one({"document_id": doc_id}) or {}
        
        # Determine Siret / Company
        extracted = ext_data.get('extracted_data', {})
        sirets = extracted.get('siret', [])
        siret = val_data.get('siret') or (sirets[0] if sirets else None)
        company = val_data.get('supplier_name') or extracted.get('company_name')
        
        # Apply Search Filters (if specified)
        if siret_filter and siret_filter not in str(siret or ''): continue
        if company_filter and company_filter.lower() not in str(company or '').lower(): continue
        
        # Anomaly status check
        doc_anomalies = list(db.anomalies.find({"document_ids": doc_id}))
        
        # Prepare for template
        doc['siret'] = siret or "Non détecté"
        doc['company_name'] = company or "Inconnu"
        # A doc is valid only if status is curated AND it has no anomalies
        doc['is_valid'] = (doc['status'] == 'curated' and len(doc_anomalies) == 0)
        doc['anomaly_causes'] = [a.get('message', 'Anomalie détectée') for a in doc_anomalies]
        enriched_docs.append(doc)
        
    print(f"DEBUG: Sending {len(enriched_docs)} docs to template")
    return render_template('documents.html', documents=enriched_docs, total=len(enriched_docs))

@app.route('/entreprises.html')
def companies():
    db = get_db()
    companies_list = list(db.companies.find().sort("nom", 1))
    
    # Enrich companies with document counts
    for company in companies_list:
        siren = company.get('siren')
        # Find document IDs associated with this company via SIRET matches in extraction or validation data
        ext_doc_ids = db.extracted_data.distinct("document_id", {"extracted_data.siret": {"$regex": f"^{siren}"}})
        val_doc_ids = db.validated_records.distinct("document_id", {"siret": {"$regex": f"^{siren}"}})
        
        unique_doc_ids = set(ext_doc_ids + val_doc_ids)
        company['doc_count'] = len(unique_doc_ids)
        
    return render_template('companies.html', companies=companies_list)

@app.route('/entreprise/<siren>')
def company_documents(siren):
    db = get_db()
    company_info = db.companies.find_one({"siren": siren})
    if not company_info:
        return redirect(url_for('companies'))
    
    # Get documents for this company
    # We'll filter all documents where extracted_data.siret starts with this siren
    # Pre-calculating a list of doc_ids might be easier
    
    # 1. Find all extracted data with this siren
    ext_matches = list(db.extracted_data.find({"extracted_data.siret": {"$regex": f"^{siren}"}}))
    val_matches = list(db.validated_records.find({"siret": {"$regex": f"^{siren}"}}))
    
    doc_ids = set([d['document_id'] for d in ext_matches] + [d['document_id'] for d in val_matches])
    
    docs = list(db.documents.find({"document_id": {"$in": list(doc_ids)}}).sort("uploaded_at", -1))
    
    enriched_docs = []
    for doc in docs:
        doc_id = doc['document_id']
        ext_data = db.extracted_data.find_one({"document_id": doc_id}) or {}
        val_data = db.validated_records.find_one({"document_id": doc_id}) or {}
        
        extracted = ext_data.get('extracted_data', {})
        sirets = extracted.get('siret', [])
        siret = val_data.get('siret') or (sirets[0] if sirets else None)
        
        doc['siret'] = siret or "Non détecté"
        doc['company_name'] = company_info.get('nom', 'Inconnu')
        doc_anomalies = list(db.anomalies.find({"document_ids": doc_id}))
        doc['is_valid'] = (doc['status'] == 'curated' and len(doc_anomalies) == 0)
        doc['anomaly_causes'] = [a.get('message', 'Anomalie détectée') for a in doc_anomalies]
        enriched_docs.append(doc)

    return render_template('company_details.html', company=company_info, documents=enriched_docs)

@app.route('/anomalie.html')
def anomalie():
    db = get_db()
    # Get all anomalies with document info
    anomalies_list = list(db.anomalies.find().sort("detected_at", -1))
    
    # Enrichment: get filenames for the document_ids
    for a in anomalies_list:
        doc_ids = a.get('document_ids', [])
        docs = list(db.documents.find({"document_id": {"$in": doc_ids}}, {"filename": 1}))
        a['filenames'] = [d['filename'] for d in docs]
        
    return render_template('anomalie.html', anomalies=anomalies_list)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)