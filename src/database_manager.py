import os
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from google.cloud import datastore
from google.cloud import logging as cloud_logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages GCP Datastore for logs and conflict resolution tracking."""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.client = datastore.Client(project=project_id)
        logger.info(f"Initialized DatabaseManager for project: {project_id}")
        
        # Initialize Cloud Logging
        try:
            cloud_logging_client = cloud_logging.Client(project=project_id)
            cloud_logging_client.setup_logging()
            logger.info("Cloud Logging initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize Cloud Logging: {str(e)}")
    
    def create_pr_record(self, pr_data: Dict[str, Any], repo_data: Dict[str, Any]) -> str:
        """Create a new PR record in Datastore."""
        try:
            pr_id = str(uuid.uuid4())
            logger.info(f"Attempting to create PR record with ID: {pr_id}")
            
            key = self.client.key("PRRecord", pr_id)
            logger.info(f"Created Datastore key for PRRecord: {pr_id}")
            
            entity = datastore.Entity(key)
            entity.update({
                "pr_number": pr_data.get("number"),
                "repo_name": repo_data.get("full_name"),
                "source_branch": pr_data.get("head", {}).get("ref"),
                "target_branch": pr_data.get("base", {}).get("ref"),
                "status": "processing",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "conflicts_detected": False,
                "files_with_conflicts": [],
                "resolution_successful": False,
                "error_message": None
            })
            
            logger.info(f"Putting entity to Datastore...")
            self.client.put(entity)
            logger.info(f"Successfully created PR record: {pr_id} for PR #{pr_data.get('number')}")
            return pr_id
        except Exception as e:
            logger.error(f"Failed to create PR record: {str(e)}")
            logger.exception("Full exception details:")
            raise
    
    def update_pr_status(self, pr_id: str, status: str, **kwargs):
        """Update PR status and additional fields."""
        key = self.client.key("PRRecord", pr_id)
        entity = self.client.get(key)
        
        if entity:
            entity["status"] = status
            entity["updated_at"] = datetime.utcnow()
            
            # Update additional fields
            for key_name, value in kwargs.items():
                entity[key_name] = value
            
            self.client.put(entity)
            logger.info(f"Updated PR {pr_id} status to: {status}")
        else:
            logger.error(f"PR record not found: {pr_id}")
    
    def log_conflict_detection(self, pr_id: str, conflicting_files: List[str]):
        """Log conflict detection for a PR."""
        self.update_pr_status(
            pr_id, 
            "conflicts_detected",
            conflicts_detected=True,
            files_with_conflicts=conflicting_files
        )
        logger.info(f"Logged conflict detection for PR {pr_id}: {conflicting_files}")
    
    def log_resolution_attempt(self, pr_id: str, file_path: str, success: bool, error_msg: str = None):
        """Log individual file resolution attempt."""
        resolution_id = str(uuid.uuid4())
        
        key = self.client.key("ResolutionRecord", resolution_id)
        
        entity = datastore.Entity(key)
        entity.update({
            "pr_id": pr_id,
            "file_path": file_path,
            "success": success,
            "error_message": error_msg,
            "created_at": datetime.utcnow()
        })
        
        self.client.put(entity)
        logger.info(f"Logged resolution attempt for {file_path}: {'SUCCESS' if success else 'FAILED'}")
    
    def log_validation_result(self, pr_id: str, success: bool, output: str):
        """Log validation results."""
        self.update_pr_status(
            pr_id,
            "validation_completed" if success else "validation_failed",
            validation_successful=success,
            validation_output=output[:500]  # Limit to 500 chars
        )
        logger.info(f"Logged validation result for PR {pr_id}: {'PASSED' if success else 'FAILED'}")
    
    def log_completion(self, pr_id: str, success: bool, error_msg: str = None):
        """Log final completion status."""
        self.update_pr_status(
            pr_id,
            "completed" if success else "failed",
            resolution_successful=success,
            error_message=error_msg
        )
        logger.info(f"Logged completion for PR {pr_id}: {'SUCCESS' if success else 'FAILED'}")
    
    def get_pr_history(self, repo_name: str, limit: int = 50) -> List[Dict]:
        """Get recent PR processing history for a repository."""
        query = self.client.query(kind="PRRecord")
        query.add_filter("repo_name", "=", repo_name)
        query.order = ["-created_at"]
        results = list(query.fetch(limit=limit))
        
        return [
            {
                "pr_id": result.key.id_or_name,
                "pr_number": result.get("pr_number"),
                "status": result.get("status"),
                "created_at": result.get("created_at"),
                "conflicts_detected": result.get("conflicts_detected", False),
                "resolution_successful": result.get("resolution_successful", False)
            }
            for result in results
        ]
    
    def get_resolution_details(self, pr_id: str) -> List[Dict]:
        """Get detailed resolution attempts for a PR."""
        query = self.client.query(kind="ResolutionRecord")
        query.add_filter("pr_id", "=", pr_id)
        query.order = ["created_at"]
        results = list(query.fetch())
        
        return [
            {
                "file_path": result.get("file_path"),
                "success": result.get("success"),
                "error_message": result.get("error_message"),
                "created_at": result.get("created_at")
            }
            for result in results
        ]
