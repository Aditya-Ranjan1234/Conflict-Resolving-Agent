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
- **Cloud Datastore API**: For storing PR logs and metadata.
- **Cloud Storage API**: For storing conflict files and edit history.
- **Cloud Logging API**: For enhanced logging capabilities.

## Step 3: Set up Authentication
1. Go to **IAM & Admin > Service Accounts**.
2. Click **Create Service Account**.
3. Name it `conflict-agent-sa`.
4. Grant it the following roles:
   - `Vertex AI User`
   - `Cloud Build Editor`
   - `Secret Manager Secret Accessor`
   - `Logs Writer`
   - `Cloud Datastore User`
   - `Storage Object Admin`
   - `Logging Admin`
5. Click **Create and Continue**, then **Done**.

## Step 4: Create Cloud Datastore Database
1. Go to **Datastore** → **Entities** (or visit: `console.cloud.google.com/datastore/setup`)
2. If you see "Create a Cloud Datastore or Cloud Firestore database", click **Create Database**
3. **Database Type**: Choose **Cloud Datastore** (not Firestore)
4. **Region**: Select the same region as your Cloud Run service (e.g., `us-central1`)
5. Click **Create Database**
6. Wait for the database to be initialized (takes 1-2 minutes)

## Step 5: Store GitHub Token in Secret Manager
1. Go to **Security > Secret Manager**.
2. Click **Create Secret**.
3. Name it `GITHUB_TOKEN`.
4. Paste your GitHub Personal Access Token (PAT) as the secret value.
5. Click **Create Secret**.

## Step 6: Deploy to Cloud Run (Manual Console Method)
To deploy your agent directly from the GCP website:

1. Go to the **[Cloud Run](https://console.cloud.google.com/run)** page in the GCP Console.
2. Click **CREATE SERVICE**.
3. Choose **"Continuously deploy new revisions from a source repository"**.
4. Click **SET UP WITH CLOUD BUILD**.
   - **Repository Provider**: Select **GitHub**.
   - **Repository**: Select your `conflict-resolving-agent` repository (you may need to authenticate GitHub first).
   - Click **Next**.
   - **Build Configuration**:
     - **Branch**: Select `main`.
     - **Build Type**: Select **Dockerfile**.
     - **Source location**: `/Dockerfile`.
     - Click **Save**.
5. **Service Settings**:
   - **Service Name**: `conflict-agent`.
   - **Region**: Choose `us-central1`.
   - **Authentication**: Select **"Allow unauthenticated invocations"** (This allows GitHub webhooks to reach the URL).
6. **Container, Networking, Security** (Expand this section):
   - **Variables & Secrets** tab:
     - Click **ADD VARIABLE**:
       - Name: `GCP_PROJECT_ID`
       - Value: `[YOUR_PROJECT_ID]`
     - Click **ADD VARIABLE** (Optional):
       - Name: `STORAGE_BUCKET_NAME`
       - Value: `custom-bucket-name` (leave empty to use auto-generated)
     - Click **REFERENCE A SECRET**:
       - Select `GITHUB_TOKEN`.
       - Version: `latest`.
       - Name: `GITHUB_TOKEN` (This is how it will be exposed as an env var).
7. Click **CREATE**.
8. Wait for the deployment to finish. Once done, copy the **Service URL** (e.g., `https://conflict-agent-xxxx.run.app`).

## Step 7: Configure GitHub Webhook
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

---

## 📊 New Features: Database & Storage

### What's Added:
- **GCP Datastore**: Stores PR processing logs, status tracking, and resolution history
- **Google Cloud Storage**: Stores conflict files, resolved versions, git diffs, and edit summaries
- **Enhanced Logging**: Cloud Logging integration for better monitoring

### API Endpoints:
- `GET /history/{repo_name}` - Get PR processing history
- `GET /pr/{pr_id}/details` - Get detailed PR processing information
- `GET /pr/{pr_id}/conflicts` - Get conflict files for a specific PR

### Storage Structure:
```
your-project-storage/
├── conflicts/{pr_id}/
│   ├── timestamp_file_conflict.py
│   └── timestamp_file_resolved.py
├── summaries/{pr_id}/
│   └── timestamp_edit_summary.json
├── validation/{pr_id}/
│   └── timestamp_validation.json
└── diffs/{pr_id}/
    └── timestamp_changes.diff
```

### Database Schema:
- **PRRecord**: Main PR tracking (status, timestamps, conflict info)
- **ResolutionRecord**: Individual file resolution attempts

### Monitoring:
- Check Cloud Logging for detailed process logs
- Use Cloud Console to browse Datastore entities
- Access Cloud Storage bucket to view conflict files
- Monitor costs in GCP Billing dashboard
