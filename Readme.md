# ScanDocs AI — Système de Détection de Fraude Documentaire

**ScanDocs AI** est une solution complète d'automatisation et de sécurisation du traitement des documents administratifs (factures, devis, attestations). Le projet combine OCR haute performance, analyse de données et moteur de règles métier pour détecter instantanément les fraudes et les erreurs de conformité.

---

## Présentation du Projet

Dans un contexte de digitalisation croissante, la falsification de documents administratifs est un risque majeur. **ScanDocs AI** répond à ce défi en proposant un pipeline de traitement intelligent qui transforme des images ou PDFs bruts en données certifiées.

### Objectifs Clés :
*   **Automatisation** : Suppression de la saisie manuelle via un OCR multi-langues.
*   **Sécurisation** : Détection automatique des incohérences financières et administratives.
*   **Conformité (KYC/KYB)** : Vérification systématique des SIRET et des périodes de validité.
*   **Gouvernance** : Traçabilité complète des données via une architecture Medallion (Raw → Clean → Curated).

---

## Architecture du Système

Le projet repose sur une architecture robuste et scalable, orchestrée par **Docker**.

### 1. Pipeline de Données (Medallion)
Le flux de données est segmenté en trois zones distinctes dans le Data Lake (MongoDB) :
*   **Zone Bronze (Raw)** : Stockage des documents originaux (PDF/JPG) sans modification.
*   **Zone Silver (Clean)** : Données extraites par l'OCR, nettoyées et structurées au format JSON.
*   **Zone Gold (Curated)** : Données validées par le moteur de règles, prêtes pour l'exploitation métier.

### 2. Moteur de Détection d'Anomalies
Notre système identifie 6 types de fraudes/erreurs critiques :
*   **MATH_ERROR** : Incohérence arithmétique (`HT + TVA != TTC`).
*   **TVA_WRONG** : Taux de TVA incorrect ou mal calculé.
*   **SIRET_MISSING/INVALID** : SIRET absent ou format incorrect.
*   **SIRET_DB_MISSING** : Entreprise inconnue dans la base SIRENE (données réelles).
*   **EXPIRED_DATE** : Document datant de plus d'un an (périmé).
*   **EXPIRED_ATTESTATION** : Attestation de vigilance dont la date de validité est dépassée.

---

## Stack Technique

*   **Langage** : Python 3.11 (Cœur du traitement)
*   **Traitement d'Image** : OpenCV, Pillow (Prétraitement & Robustesse)
*   **OCR** : Tesseract (Moteur de reconnaissance de caractères)
*   **Base de Données** : MongoDB (NoSQL pour la flexibilité des documents)
*   **Frontend Duo** : 
    *   **Flask (TailwindCSS)** : Interface métier fluide pour la gestion quotidienne.
    *   **Streamlit** : Dashboard analytique pour le suivi des KPIs de risque.
*   **Infrastructure** : Docker & Docker-Compose.

---

## Démarrage Rapide

### 1. Lancer l'infrastructure complète
Assurez-vous d'avoir Docker installé, puis lancez le projet à la racine :
```bash
docker-compose up --build -d
```
Les services seront accessibles aux adresses suivantes :
*   **App Métier (Flask)** : `http://localhost:5000`
*   **Dashboard Analytics (Streamlit)** : `http://localhost:8501`
*   **API Backend** : `http://localhost:8000`

### 2. Générer le Dataset de test (Optionnel)
Pour tester le système avec des documents réalistes contenant des anomalies injectées :

```powershell
# 1. Configurer l'accès à la base de données (Docker port 27027)
$env:MONGO_URI = "mongodb://localhost:27027/hackathon"

# 2. Importer les entreprises de la base SIRENE réelle
python dataset/generator/import_companies.py

# 3. Générer 130+ documents (Factures, Devis, KBIS...) avec anomalies
python dataset/generator/generate_invoices.py
```
*Les documents seront générés dans `dataset/generator/generated/` et pourront être uploadés via l'interface.*

---

## Fonctionnalités Avancées

*   **Réalisme des documents** : Le générateur applique des effets de photo (grain, bruit, rotation légère) pour simuler des conditions réelles d'utilisation par smartphone.
*   **Extraction de précision** : Utilisation de Regex contextuelles pour capturer les montants même dans des mises en page complexes (CAS A/B).
*   **Centre d'Alertes** : Interface dédiée listant chaque anomalie avec sa cause précise et son niveau de sévérité.

---

*Projet réalisé par l'équipe IPSSI dans le cadre du Hackathon IA & Data.*
