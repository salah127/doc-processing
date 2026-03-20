from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27027/hackathon")
db = client.hackathon

curated_ids = [d["document_id"] for d in db.documents.find({"status": "curated"})]
anomaly_docs = set()
for a in db.anomalies.find():
    for d_id in a.get("document_ids", []):
        anomaly_docs.add(d_id)

print(f"Total curated: {len(curated_ids)}")
print(f"Total anomalies docs count: {db.anomalies.count_documents({})}")
print(f"Unique Docs with anomaly: {len(anomaly_docs)}")
print(f"Docs without anomaly: {len([i for i in curated_ids if i not in anomaly_docs])}")
