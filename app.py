import streamlit as st
import requests
import pandas as pd
import os
import json
from pymongo import MongoClient

# --- CONFIG ---
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/hackathon")


# --- DB HELPERS ---
@st.cache_resource
def get_db():
    uris = [
        os.getenv("MONGO_URI", "mongodb://mongodb:27017/hackathon"),
        "mongodb://localhost:27027/hackathon",
        "mongodb://localhost:27017/hackathon",
    ]
    for uri in uris:
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=2000)
            client.admin.command("ping")
            return client.hackathon
        except:
            continue
    return None

db = get_db()
if db is None:
    st.error("⚠️ Connexion à MongoDB échouée. Vérifiez votre configuration.")
    st.stop()

# --- APP ---
st.title("🛡️ Dashboard de Fraude & Conformité")
st.markdown("Système de vérification automatisée de documents")
st.markdown("---")

tabs = st.tabs(["📊 Vue d'ensemble", "🔍 Validation & Anomalies", "📂 Explorateur de Données", "📤 Batch Upload"])

with tabs[0]:
    st.header("État du Système")
    
    try:
        total_docs = db.documents.count_documents({})
        anomalies_count = db.anomalies.count_documents({})
        valid_count = total_docs - anomalies_count
        anomaly_rate = (anomalies_count / total_docs * 100) if total_docs > 0 else 0
        
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Documents Traités", total_docs)
        kpi2.metric("Documents Valides", valid_count)
        kpi3.metric("Anomalies Détectées", anomalies_count, delta=f"{anomaly_rate:.1f}% Risque", delta_color="inverse")
        kpi4.metric("En attente (Raw)", db.documents.count_documents({"status": "raw"}))
        
        st.markdown("---")
        
        col_left, col_right = st.columns(2)
        
        with col_left:
            st.subheader("⚠️ Types d'Anomalies")
            anomalies_list = list(db.anomalies.find({}, {"rule_code": 1, "_id": 0}))
            if anomalies_list:
                df_fraud = pd.DataFrame(anomalies_list)
                if 'rule_code' in df_fraud.columns:
                    counts = df_fraud['rule_code'].value_counts()
                    st.bar_chart(counts, color="#FF4B4B")
                else:
                    st.info("Attente de données de validation...")
            else:
                st.info("Aucune anomalie détectée pour le moment.")
                
        with col_right:
            st.subheader("📄 Répartition par Type")
            docs_list = list(db.documents.find({}, {"predicted_type": 1, "_id": 0}))
            if docs_list:
                df_types = pd.DataFrame(docs_list)
                # Fix: Using 'predicted_type' consistently
                if 'predicted_type' in df_types.columns:
                    st.bar_chart(df_types['predicted_type'].value_counts(), color="#4B8BFF")
                else:
                    st.info("Attente de classification...")
            else:
                st.info("Aucun document analysé.")

    except Exception as e:
        st.error(f"Erreur lors de la récupération des stats: {e}")

with tabs[1]:
    st.header("🛡️ Centre de Contrôle des Fraudes")
    st.write("Analyse détaillée des problèmes de conformité détectés.")
    
    anomalies = list(db.anomalies.find().sort("detected_at", -1))
    
    if anomalies:
        for idx, a in enumerate(anomalies):
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 4, 1])
                sev = a.get("severity", "medium").upper()
                emoji = "🔴" if sev == "HIGH" else "🟠" if sev == "MEDIUM" else "🟡"
                
                c1.markdown(f"### {emoji}\n**{sev}**")
                
                doc_ids = a.get("document_ids", [])
                filenames = []
                if doc_ids:
                    docs = list(db.documents.find({"document_id": {"$in": doc_ids}}, {"filename": 1}))
                    filenames = [d["filename"] for d in docs]
                
                c2.markdown(f"**Cause : {a.get('message', 'Non spécifiée')}**")
                c2.caption(f"Règle : `{a.get('rule_code')}` | Date : {a.get('detected_at')}")
                if filenames:
                    c2.markdown(f"*Fichiers : {', '.join(filenames)}*")
                
                if c3.button("Détails", key=f"det_{idx}"):
                    st.info(f"Information complémentaire : {a.get('message')}")
                    
    else:
        st.success("✅ Félicitations ! Aucun document frauduleux ou erroné détecté.")

with tabs[2]:
    st.header("📂 Explorateur de Données")
    zone = st.selectbox("Choisir la zone du Data Lake", ["Raw (Bronze)", "Clean (Silver)", "Curated (Gold)"])
    layer = zone.split(" ")[0].lower()
    base_data = "data"
    layer_dir = f"{base_data}/{layer}"
    
    if os.path.exists(layer_dir):
        files = [f for f in os.listdir(layer_dir) if os.path.isfile(os.path.join(layer_dir, f))]
        if files:
            selected_file = st.selectbox("Sélectionner un fichier", files)
            file_path = os.path.join(layer_dir, selected_file)
            
            with st.expander(f"Contenu : {selected_file}", expanded=True):
                if selected_file.endswith('.json'):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        st.json(data)
                        if layer == "curated":
                             st.success(f"Classification : `{data.get('predicted_type', 'Inconnue')}`")
                elif selected_file.endswith('.txt'):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        st.text(f.read())
                else:
                    st.write("Format non textuel (Image/PDF)")
        else:
            st.info(f"La zone {zone} est vide.")
    else:
        st.warning(f"Répertoire {layer_dir} introuvable.")

with tabs[3]:
    st.header("📤 Pipeline de Traitement")
    st.write("Ajouter des documents à la file d'attente.")
    
    files = st.file_uploader(
        "Déposez vos documents ici", 
        type=['pdf', 'jpg', 'png', 'jpeg'], 
        accept_multiple_files=True
    )
    
    if files:
        if st.button("🚀 Démarrer le traitement", width="stretch"):
            bar = st.progress(0)
            try:
                payload = [("files", (f.name, f.getvalue(), f.type)) for f in files]
                bar.progress(20)
                r = requests.post(f"{BACKEND_URL}/upload", files=payload)
                bar.progress(100)
                
                if r.status_code == 200:
                    res = r.json()
                    st.success(f"Analysé : {len(res.get('results', []))} fichiers.")
                    with st.expander("Résultat détaillé"):
                         st.json(res)
                else:
                    st.error(f"Erreur Serveur ({r.status_code})")
            except Exception as e:
                st.error(f"Erreur de connexion : {e}")

# Sidebar
st.sidebar.title("Paramètres")
st.sidebar.markdown(f"**Serveur Backend:** `{BACKEND_URL}`")
st.sidebar.info("Architecture Medallion : Flux de données Raw → Clean → Curated")
if st.sidebar.button("Rafraîchir"):
    st.rerun()

