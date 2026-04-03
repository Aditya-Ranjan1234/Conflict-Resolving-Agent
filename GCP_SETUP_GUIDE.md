# 🚀 Google Cloud Platform (GCP) Setup Guide

This guide will walk you through setting up the Conflict Resolving Agent on GCP from scratch.

## Step 1: Create a GCP Project
1. Go to the [GCP Console](https://console.cloud.google.com/).
2. Click on the project dropdown at the top and select **New Project**.
3. Name it (e.g., `conflict-resolving-agent`) and click **Create**.
4. Note your **Project ID**.

## Step 2: Enable APIs
Enable the following APIs in the **API & Services > Library** section:
- **Vertex AI API**: For the AI resolution engine.
- **Cloud Run API**: For hosting the backend service.
- **Cloud Build API**: For CI/CD and validation.
- **Secret Manager API**: To securely store your GitHub Token.

## Step 3: Set up Authentication
1. Go to **IAM & Admin > Service Accounts**.
2. Click **Create Service Account**.
3. Name it `conflict-agent-sa`.
4. Grant it the following roles:
   - `Vertex AI User`
   - `Cloud Build Editor`
   - `Secret Manager Secret Accessor`
   - `Logs Writer`
5. Click **Create and Continue**, then **Done**.

## Step 4: Store GitHub Token in Secret Manager
1. Go to **Security > Secret Manager**.
2. Click **Create Secret**.
3. Name it `GITHUB_TOKEN`.
4. Paste your GitHub Personal Access Token (PAT) as the secret value.
5. Click **Create Secret**.

## Step 5: Deploy to Cloud Run
You can deploy using the Google Cloud CLI (`gcloud`) from your local machine:

1. Authenticate:
   ```bash
   gcloud auth login
   ```
2. Set your project:
   ```bash
   gcloud config set project [YOUR_PROJECT_ID]
   ```
3. Deploy:
   ```bash
   gcloud run deploy conflict-agent \
     --source . \
     --region us-central1 \
     --allow-unauthenticated \
     --set-env-vars GCP_PROJECT_ID=[YOUR_PROJECT_ID] \
     --set-secrets GITHUB_TOKEN=GITHUB_TOKEN:latest
   ```
4. Note the **Service URL** provided at the end (e.g., `https://conflict-agent-xxxx.run.app`).

## Step 6: Configure GitHub Webhook
1. Go to your GitHub repository **Settings > Webhooks**.
2. Click **Add webhook**.
3. Set **Payload URL** to: `[YOUR_SERVICE_URL]/webhook`.
4. Set **Content type** to: `application/json`.
5. Select **Let me select individual events** and check:
   - Pull requests
6. Click **Add webhook**.

---

## 🧪 Testing Your Setup
1. Create a Pull Request in your repo that has a merge conflict.
2. Watch the logs in Cloud Run to see the agent detect and resolve it.
3. If validation passes, you should see a new commit on the PR branch with the fix!
