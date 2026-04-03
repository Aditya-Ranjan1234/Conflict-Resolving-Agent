import os
import logging
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from .git_manager import GitManager
from .ai_resolver import AIResolver
from .validator import Validator

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Conflict Resolving Agent API")

# Configuration from environment variables
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# Initialize components
git_manager = GitManager()
# Note: AIResolver requires a valid GCP Project ID to initialize Vertex AI
# We initialize it inside the handler to handle cases where project_id might be missing
ai_resolver: Optional[AIResolver] = None
if GCP_PROJECT_ID:
    ai_resolver = AIResolver(project_id=GCP_PROJECT_ID, location=GCP_LOCATION)

class WebhookPayload(BaseModel):
    action: str
    pull_request: Optional[Dict[str, Any]] = None
    repository: Optional[Dict[str, Any]] = None

@app.get("/")
async def root():
    return {"message": "Conflict Resolving Agent is running!"}

@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint for GitHub Webhooks.
    Handles 'pull_request' events with actions like 'opened' or 'synchronize'.
    """
    # Verify GitHub signature (optional but recommended)
    # verify_signature(request)
    
    payload = await request.json()
    action = payload.get("action")
    pr_data = payload.get("pull_request")
    
    if action in ["opened", "synchronize"] and pr_data:
        # Check if the PR has merge conflicts
        # GitHub might not compute mergeable state immediately, so we process it in background
        background_tasks.add_task(process_pull_request, payload)
        return {"status": "Processing pull request in background"}
    
    return {"status": "Event ignored"}

async def process_pull_request(payload: Dict[str, Any]):
    """Background task to handle conflict resolution."""
    pr_data = payload.get("pull_request")
    repo_data = payload.get("repository")
    
    if not pr_data or not repo_data:
        logger.error("Incomplete payload for PR processing")
        return

    repo_url = repo_data.get("clone_url")
    repo_name = repo_data.get("full_name").replace("/", "_")
    source_branch = pr_data.get("head", {}).get("ref")
    target_branch = pr_data.get("base", {}).get("ref")
    pr_number = pr_data.get("number")

    logger.info(f"Processing PR #{pr_number} on {repo_name}: {source_branch} -> {target_branch}")

    try:
        # 1. Clone Repo
        repo_path = git_manager.clone_repo(repo_url, repo_name, GITHUB_TOKEN)
        
        # 2. Attempt Merge and Detect Conflicts
        conflicting_files = git_manager.attempt_merge(repo_path, source_branch, target_branch)
        
        if not conflicting_files:
            logger.info(f"No conflicts detected for PR #{pr_number}")
            git_manager.cleanup(repo_path)
            return

        logger.info(f"Conflicts detected in files: {conflicting_files}")

        # 3. AI Resolution
        if not ai_resolver:
            logger.error("AIResolver not initialized. Missing GCP_PROJECT_ID?")
            return

        for file_path in conflicting_files:
            logger.info(f"Resolving conflict in {file_path}")
            conflict_content = git_manager.get_conflict_context(repo_path, file_path)
            
            # Resolve conflict using AI
            resolved_content = ai_resolver.resolve_conflict(file_path, conflict_content)
            
            # Apply resolution
            git_manager.apply_resolution(repo_path, file_path, resolved_content)

        # 4. Validation
        validator = Validator(repo_path)
        test_command = validator.detect_test_command()
        success, output = validator.run_validation(test_command)

        if success:
            logger.info(f"Validation passed for PR #{pr_number}")
            # 5. Commit and Push
            git_manager.commit_and_push(
                repo_path, 
                source_branch, 
                f"Resolved merge conflicts by AI Agent for PR #{pr_number}"
            )
            # 6. Post Comment to PR (Optional - requires GitHub API client like PyGithub)
            # post_comment_to_github(repo_data.get("full_name"), pr_number, "Conflict resolved by AI agent!")
        else:
            logger.error(f"Validation failed for PR #{pr_number}:\n{output}")
            # TODO: Handle retry logic or notify human

        # Cleanup
        git_manager.cleanup(repo_path)

    except Exception as e:
        logger.exception(f"Error processing PR #{pr_number}: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
