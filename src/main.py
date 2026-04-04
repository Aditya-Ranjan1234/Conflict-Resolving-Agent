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

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('conflict_resolver.log')
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Conflict Resolving Agent API")

# Configuration from environment variables
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# Log configuration (without sensitive data)
logger.info("=== Configuration ===")
logger.info(f"GCP_PROJECT_ID: {GCP_PROJECT_ID}")
logger.info(f"GCP_LOCATION: {GCP_LOCATION}")
logger.info(f"GITHUB_TOKEN: {'***SET***' if GITHUB_TOKEN else 'NOT_SET'}")
logger.info(f"WEBHOOK_SECRET: {'***SET***' if WEBHOOK_SECRET else 'NOT_SET'}")
logger.info("====================")

# Initialize components
logger.info("Initializing GitManager...")
git_manager = GitManager()
# Note: AIResolver requires a valid GCP Project ID to initialize Vertex AI
# We initialize it inside the handler to handle cases where project_id might be missing
ai_resolver: Optional[AIResolver] = None
if GCP_PROJECT_ID:
    logger.info(f"Initializing AIResolver with project_id: {GCP_PROJECT_ID}")
    ai_resolver = AIResolver(project_id=GCP_PROJECT_ID, location=GCP_LOCATION)
else:
    logger.warning("GCP_PROJECT_ID not found. AI resolution will not be available.")

class WebhookPayload(BaseModel):
    action: str
    pull_request: Optional[Dict[str, Any]] = None
    repository: Optional[Dict[str, Any]] = None

@app.get("/")
async def root():
    logger.info("Health check endpoint accessed")
    return {"message": "Conflict Resolving Agent is running!"}

@app.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint for GitHub Webhooks.
    Handles 'pull_request' events with actions like 'opened' or 'synchronize'.
    """
    logger.info("Webhook received")
    
    # Verify GitHub signature (optional but recommended)
    # verify_signature(request)
    
    try:
        payload = await request.json()
        logger.info(f"Webhook payload received: {payload.get('action', 'unknown')} action")
        action = payload.get("action")
        pr_data = payload.get("pull_request")
        
        if action in ["opened", "synchronize"] and pr_data:
            logger.info(f"Processing {action} action for PR")
            # Check if the PR has merge conflicts
            # GitHub might not compute mergeable state immediately, so we process it in background
            background_tasks.add_task(process_pull_request, payload)
            logger.info("Added PR processing to background tasks")
            return {"status": "Processing pull request in background"}
        else:
            logger.info(f"Ignoring action: {action}")
            return {"status": "Event ignored"}
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        raise

async def process_pull_request(payload: Dict[str, Any]):
    """Background task to handle conflict resolution."""
    logger.info("Starting PR processing...")
    
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
    logger.info(f"Repository URL: {repo_url}")

    repo_path = None
    try:
        # 1. Clone Repo
        logger.info("Step 1: Cloning repository...")
        repo_path = git_manager.clone_repo(repo_url, repo_name, GITHUB_TOKEN)
        logger.info(f"Repository cloned to: {repo_path}")
        
        # 2. Attempt Merge and Detect Conflicts
        logger.info("Step 2: Attempting merge to detect conflicts...")
        conflicting_files = git_manager.attempt_merge(repo_path, source_branch, target_branch)
        
        if not conflicting_files:
            logger.info(f"No conflicts detected for PR #{pr_number}")
            git_manager.cleanup(repo_path)
            return

        logger.info(f"Conflicts detected in files: {conflicting_files}")

        # 3. AI Resolution
        logger.info("Step 3: Starting AI conflict resolution...")
        if not ai_resolver:
            logger.error("AIResolver not initialized. Missing GCP_PROJECT_ID?")
            return

        for file_path in conflicting_files:
            logger.info(f"Resolving conflict in {file_path}")
            try:
                conflict_content = git_manager.get_conflict_context(repo_path, file_path)
                logger.info(f"Retrieved conflict context for {file_path} ({len(conflict_content)} chars)")
                
                # Resolve conflict using AI
                resolved_content = ai_resolver.resolve_conflict(file_path, conflict_content)
                logger.info(f"AI resolution completed for {file_path} ({len(resolved_content)} chars)")
                
                # Apply resolution
                git_manager.apply_resolution(repo_path, file_path, resolved_content)
                logger.info(f"Applied resolution for {file_path}")
            except Exception as e:
                logger.error(f"Error resolving conflict in {file_path}: {str(e)}")
                raise

        # 4. Validation
        logger.info("Step 4: Running validation...")
        validator = Validator(repo_path)
        test_command = validator.detect_test_command()
        logger.info(f"Detected test command: {test_command}")
        
        try:
            success, output = validator.run_validation(test_command)
            logger.info(f"Validation result: success={success}, output_length={len(output)}")
            if output:
                logger.debug(f"Validation output: {output[:500]}...")  # Log first 500 chars
        except Exception as e:
            logger.error(f"Error during validation: {str(e)}")
            success = False
            output = str(e)

        if success:
            logger.info(f"Validation passed for PR #{pr_number}")
            # 5. Commit and Push
            logger.info("Step 5: Committing and pushing changes...")
            try:
                git_manager.commit_and_push(
                    repo_path, 
                    source_branch, 
                    f"Resolved merge conflicts by AI Agent for PR #{pr_number}",
                    GITHUB_TOKEN
                )
                logger.info(f"Successfully committed and pushed resolved conflicts for PR #{pr_number}")
            except Exception as e:
                logger.error(f"Failed to commit and push for PR #{pr_number}: {str(e)}")
                logger.exception("Full exception details:")
                raise
            # 6. Post Comment to PR (Optional - requires GitHub API client like PyGithub)
            # post_comment_to_github(repo_data.get("full_name"), pr_number, "Conflict resolved by AI agent!")
        else:
            logger.error(f"Validation failed for PR #{pr_number}:\n{output}")
            # TODO: Handle retry logic or notify human

        # Cleanup
        logger.info("Step 6: Cleaning up repository...")
        if repo_path:
            git_manager.cleanup(repo_path)
        logger.info(f"PR processing completed for #{pr_number}")

    except Exception as e:
        logger.exception(f"Error processing PR #{pr_number}: {str(e)}")
        logger.error(f"Full error details: {type(e).__name__}: {str(e)}")
        if repo_path:
            try:
                logger.info("Attempting cleanup after error...")
                git_manager.cleanup(repo_path)
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup: {str(cleanup_error)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    logger.info(f"Starting Conflict Resolving Agent on port {port}")
    logger.info("=== Application Startup Complete ===")
    uvicorn.run(app, host="0.0.0.0", port=port)
