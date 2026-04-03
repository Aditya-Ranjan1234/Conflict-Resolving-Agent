# Conflict Resolving Agent 🤖

An AI agent that automatically detects, understands, and resolves Git merge conflicts with minimal human intervention.

## 🏗️ System Architecture (GCP)
1. **Trigger Layer**: GitHub Webhooks → Cloud Run
2. **Detection Service**: Cloud Run pulls repo and runs `git merge`.
3. **AI Resolution Engine**: Vertex AI (Gemini) resolves conflicts.
4. **Validation Layer**: Cloud Build runs tests.
5. **Auto Commit**: Pushes fixed code back to GitHub.

## 🚀 Setup & Deployment
Refer to `GCP_SETUP_GUIDE.md` for detailed instructions on setting up the Google Cloud Console from scratch.

## 🛠️ Local Development
1. Create a virtual environment: `python -m venv venv`
2. Activate: `.\venv\Scripts\activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Run the service: `python src/main.py`
