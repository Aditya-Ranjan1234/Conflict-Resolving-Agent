# Conflict Resolving Agent 🤖

## 📌 Overview
This project is an AI-based conflict resolving agent...

## 🚀 Features
- Natural language conflict resolution
- Context-aware responses
- Scalable architecture

## 🛠 Tech Stack
- Python
- LLM APIs
- Flask (if used)

## ☁️ Deployment on GCP

### 1. Create a Project
- Go to Google Cloud Console
- Create a new project

### 2. Enable APIs
- Enable Compute Engine / Cloud Run

### 3. Deploy using Cloud Run
```bash
gcloud run deploy conflict-agent \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated