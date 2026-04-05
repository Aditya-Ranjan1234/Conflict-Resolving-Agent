import os
import logging
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from .git_manager import GitManager
from .ai_resolver import AIResolver
from .validator import Validator
from .database_manager import DatabaseManager
from .storage_manager import StorageManager

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
STORAGE_BUCKET_NAME = os.getenv("STORAGE_BUCKET_NAME")  # Optional, will use default if not set

# Log configuration (without sensitive data)
logger.info("=== Configuration ===")
logger.info(f"GCP_PROJECT_ID: {GCP_PROJECT_ID}")
logger.info(f"GCP_LOCATION: {GCP_LOCATION}")
logger.info(f"GITHUB_TOKEN: {'***SET***' if GITHUB_TOKEN else 'NOT_SET'}")
logger.info(f"WEBHOOK_SECRET: {'***SET***' if WEBHOOK_SECRET else 'NOT_SET'}")
logger.info(f"STORAGE_BUCKET_NAME: {STORAGE_BUCKET_NAME or 'AUTO_GENERATED'}")
logger.info("====================")

# Initialize components
logger.info("Initializing GitManager...")
git_manager = GitManager()

# Initialize Database and Storage managers
db_manager: Optional[DatabaseManager] = None
storage_manager: Optional[StorageManager] = None

if GCP_PROJECT_ID:
    try:
        logger.info("Initializing DatabaseManager...")
        db_manager = DatabaseManager(project_id=GCP_PROJECT_ID)
        
        logger.info("Initializing StorageManager...")
        storage_manager = StorageManager(project_id=GCP_PROJECT_ID, bucket_name=STORAGE_BUCKET_NAME)
        
        logger.info("Database and Storage managers initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Database/Storage managers: {str(e)}")
        # Continue without them - functionality will be limited
else:
    logger.warning("GCP_PROJECT_ID not found. Database and Storage will not be available.")

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

@app.get("/history/{repo_name}")
async def get_pr_history(repo_name: str, limit: int = 50):
    """Get PR processing history for a repository."""
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    
    try:
        history = db_manager.get_pr_history(repo_name, limit)
        return {"repository": repo_name, "history": history}
    except Exception as e:
        logger.error(f"Error fetching history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/pr/{pr_id}/details")
async def get_pr_details(pr_id: str):
    """Get detailed information about a specific PR processing."""
    if not db_manager or not storage_manager:
        raise HTTPException(status_code=503, detail="Database or Storage not available")
    
    try:
        # Get resolution details from database
        resolution_details = db_manager.get_resolution_details(pr_id)
        
        # Get comprehensive summary from storage
        storage_summary = storage_manager.get_pr_summary(pr_id)
        
        return {
            "pr_id": pr_id,
            "resolution_details": resolution_details,
            "storage_summary": storage_summary
        }
    except Exception as e:
        logger.error(f"Error fetching PR details: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/pr/{pr_id}/conflicts")
async def get_pr_conflicts(pr_id: str):
    """Get conflict files for a specific PR."""
    if not storage_manager:
        raise HTTPException(status_code=503, detail="Storage not available")
    
    try:
        conflicts = storage_manager.get_conflict_history(pr_id)
        return {"pr_id": pr_id, "conflicts": conflicts}
    except Exception as e:
        logger.error(f"Error fetching conflicts: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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

    # Create PR record in database
    pr_id = None
    if db_manager:
        try:
            pr_id = db_manager.create_pr_record(pr_data, repo_data)
            logger.info(f"Created database record for PR: {pr_id}")
        except Exception as e:
            logger.error(f"Failed to create PR record: {str(e)}")
            # Continue without database - functionality will be limited
            db_manager = None

    repo_path = None
    edit_summary = {
        "pr_number": pr_number,
        "repo_name": repo_name,
        "source_branch": source_branch,
        "target_branch": target_branch,
        "conflicts_resolved": [],
        "errors": [],
        "timestamp": None
    }
    
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
            if db_manager and pr_id:
                db_manager.log_completion(pr_id, True, "No conflicts detected")
            git_manager.cleanup(repo_path)
            return

        logger.info(f"Conflicts detected in files: {conflicting_files}")
        
        # Log conflict detection
        if db_manager and pr_id:
            db_manager.log_conflict_detection(pr_id, conflicting_files)

        # 3. AI Resolution
        logger.info("Step 3: Starting AI conflict resolution...")
        if not ai_resolver:
            logger.error("AIResolver not initialized. Missing GCP_PROJECT_ID?")
            if db_manager and pr_id:
                db_manager.log_completion(pr_id, False, "AIResolver not initialized")
            return

        for file_path in conflicting_files:
            logger.info(f"Resolving conflict in {file_path}")
            try:
                conflict_content = git_manager.get_conflict_context(repo_path, file_path)
                logger.info(f"Retrieved conflict context for {file_path} ({len(conflict_content)} chars)")
                
                # Store conflict file in storage
                if storage_manager and pr_id:
                    storage_manager.store_conflict_file(
                        pr_id, file_path, conflict_content, "", 
                        {"branch": source_branch, "pr_number": pr_number}
                    )
                
                # Resolve conflict using AI
                resolved_content = ai_resolver.resolve_conflict(file_path, conflict_content)
                logger.info(f"AI resolution completed for {file_path} ({len(resolved_content)} chars)")
                
                # Apply resolution
                git_manager.apply_resolution(repo_path, file_path, resolved_content)
                logger.info(f"Applied resolution for {file_path}")
                
                # Store resolved file in storage
                if storage_manager and pr_id:
                    storage_manager.store_conflict_file(
                        pr_id, file_path, conflict_content, resolved_content,
                        {"branch": source_branch, "pr_number": pr_number, "status": "resolved"}
                    )
                
                # Log successful resolution
                if db_manager and pr_id:
                    db_manager.log_resolution_attempt(pr_id, file_path, True)
                
                edit_summary["conflicts_resolved"].append({
                    "file": file_path,
                    "status": "success",
                    "original_size": len(conflict_content),
                    "resolved_size": len(resolved_content)
                })
                
            except Exception as e:
                logger.error(f"Error resolving conflict in {file_path}: {str(e)}")
                if db_manager and pr_id:
                    db_manager.log_resolution_attempt(pr_id, file_path, False, str(e))
                
                edit_summary["conflicts_resolved"].append({
                    "file": file_path,
                    "status": "failed",
                    "error": str(e)
                })
                edit_summary["errors"].append(f"Failed to resolve {file_path}: {str(e)}")
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

        # Store validation results
        if storage_manager and pr_id:
            storage_manager.store_validation_log(pr_id, output, success)
        
        if db_manager and pr_id:
            db_manager.log_validation_result(pr_id, success, output)

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
                
                # Store git diff
                if storage_manager and repo_path and pr_id:
                    try:
                        import subprocess
                        diff_result = subprocess.run(
                            ["git", "diff", "HEAD~1", "HEAD"],
                            cwd=repo_path,
                            capture_output=True,
                            text=True
                        )
                        if diff_result.returncode == 0:
                            storage_manager.store_git_diff(pr_id, diff_result.stdout)
                    except Exception as e:
                        logger.error(f"Failed to store git diff: {str(e)}")
                
                # Log completion
                if db_manager and pr_id:
                    db_manager.log_completion(pr_id, True)
                
                edit_summary["status"] = "success"
                
            except Exception as e:
                logger.error(f"Failed to commit and push for PR #{pr_number}: {str(e)}")
                logger.exception("Full exception details:")
                
                if db_manager and pr_id:
                    db_manager.log_completion(pr_id, False, str(e))
                
                edit_summary["status"] = "push_failed"
                edit_summary["errors"].append(f"Push failed: {str(e)}")
                raise
        else:
            logger.error(f"Validation failed for PR #{pr_number}:\n{output}")
            
            if db_manager and pr_id:
                db_manager.log_completion(pr_id, False, f"Validation failed: {output}")
            
            edit_summary["status"] = "validation_failed"
            edit_summary["errors"].append(f"Validation failed: {output}")

        # Store edit summary
        if storage_manager and pr_id:
            from datetime import datetime
            edit_summary["timestamp"] = datetime.utcnow().isoformat()
            storage_manager.store_edit_summary(pr_id, edit_summary)

        # Cleanup
        logger.info("Step 6: Cleaning up repository...")
        if repo_path:
            git_manager.cleanup(repo_path)
        logger.info(f"PR processing completed for #{pr_number}")

    except Exception as e:
        logger.exception(f"Error processing PR #{pr_number}: {str(e)}")
        logger.error(f"Full error details: {type(e).__name__}: {str(e)}")
        
        if db_manager and pr_id:
            db_manager.log_completion(pr_id, False, str(e))
        
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
