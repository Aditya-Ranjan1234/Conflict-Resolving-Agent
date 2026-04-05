import os
import logging
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from google.cloud import storage
from google.cloud import storage as gcs

logger = logging.getLogger(__name__)

class StorageManager:
    """Manages Google Cloud Storage for storing edit history and conflict files."""
    
    def __init__(self, project_id: str, bucket_name: str = None):
        self.project_id = project_id
        self.client = storage.Client(project=project_id)
        
        # Use provided bucket name or create default
        if bucket_name:
            self.bucket_name = bucket_name
        else:
            self.bucket_name = f"{project_id}-conflict-resolver-storage"
        
        # Ensure bucket exists
        self._ensure_bucket_exists()
        logger.info(f"Initialized StorageManager with bucket: {self.bucket_name}")
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist."""
        try:
            self.client.get_bucket(self.bucket_name)
            logger.info(f"Bucket {self.bucket_name} already exists")
        except Exception:
            logger.info(f"Creating bucket {self.bucket_name}")
            bucket = self.client.create_bucket(self.bucket_name, location="us-central1")
            logger.info(f"Created bucket: {bucket.name}")
    
    def store_conflict_file(self, pr_id: str, file_path: str, conflict_content: str, 
                           resolved_content: str, metadata: Dict[str, Any] = None) -> str:
        """Store original conflict file and resolved version."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = file_path.replace("/", "_").replace("\\", "_")
        
        # Store conflict version
        conflict_blob_name = f"conflicts/{pr_id}/{timestamp}_{safe_filename}_conflict.py"
        conflict_blob = self.client.bucket(self.bucket_name).blob(conflict_blob_name)
        
        conflict_data = {
            "file_path": file_path,
            "content": conflict_content,
            "metadata": metadata or {},
            "timestamp": timestamp,
            "type": "conflict"
        }
        
        conflict_blob.upload_from_string(
            json.dumps(conflict_data, indent=2),
            content_type="application/json"
        )
        
        # Store resolved version
        resolved_blob_name = f"conflicts/{pr_id}/{timestamp}_{safe_filename}_resolved.py"
        resolved_blob = self.client.bucket(self.bucket_name).blob(resolved_blob_name)
        
        resolved_data = {
            "file_path": file_path,
            "content": resolved_content,
            "metadata": metadata or {},
            "timestamp": timestamp,
            "type": "resolved"
        }
        
        resolved_blob.upload_from_string(
            json.dumps(resolved_data, indent=2),
            content_type="application/json"
        )
        
        logger.info(f"Stored conflict/resolved files for {file_path} in PR {pr_id}")
        return conflict_blob_name
    
    def store_edit_summary(self, pr_id: str, edit_summary: Dict[str, Any]) -> str:
        """Store a summary of all edits made during conflict resolution."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        blob_name = f"summaries/{pr_id}/{timestamp}_edit_summary.json"
        
        summary_data = {
            "pr_id": pr_id,
            "timestamp": timestamp,
            "summary": edit_summary,
            "created_at": datetime.utcnow().isoformat()
        }
        
        blob = self.client.bucket(self.bucket_name).blob(blob_name)
        blob.upload_from_string(
            json.dumps(summary_data, indent=2),
            content_type="application/json"
        )
        
        logger.info(f"Stored edit summary for PR {pr_id}")
        return blob_name
    
    def store_validation_log(self, pr_id: str, validation_output: str, success: bool) -> str:
        """Store validation results."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        blob_name = f"validation/{pr_id}/{timestamp}_validation.json"
        
        validation_data = {
            "pr_id": pr_id,
            "timestamp": timestamp,
            "success": success,
            "output": validation_output,
            "created_at": datetime.utcnow().isoformat()
        }
        
        blob = self.client.bucket(self.bucket_name).blob(blob_name)
        blob.upload_from_string(
            json.dumps(validation_data, indent=2),
            content_type="application/json"
        )
        
        logger.info(f"Stored validation log for PR {pr_id}: {'PASSED' if success else 'FAILED'}")
        return blob_name
    
    def store_git_diff(self, pr_id: str, diff_content: str) -> str:
        """Store the git diff showing what changes were made."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        blob_name = f"diffs/{pr_id}/{timestamp}_changes.diff"
        
        blob = self.client.bucket(self.bucket_name).blob(blob_name)
        blob.upload_from_string(
            diff_content,
            content_type="text/plain"
        )
        
        logger.info(f"Stored git diff for PR {pr_id}")
        return blob_name
    
    def get_conflict_history(self, pr_id: str) -> list:
        """Get all conflict files for a specific PR."""
        prefix = f"conflicts/{pr_id}/"
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        
        files = []
        for blob in blobs:
            try:
                content = blob.download_as_text()
                files.append({
                    "name": blob.name,
                    "size": blob.size,
                    "created": blob.time_created,
                    "content": json.loads(content)
                })
            except Exception as e:
                logger.error(f"Error reading blob {blob.name}: {str(e)}")
        
        return files
    
    def get_pr_summary(self, pr_id: str) -> Dict[str, Any]:
        """Get a comprehensive summary of all files related to a PR."""
        summary = {
            "pr_id": pr_id,
            "conflicts": [],
            "summaries": [],
            "validation": [],
            "diffs": []
        }
        
        # Get conflicts
        conflicts = self.get_conflict_history(pr_id)
        summary["conflicts"] = conflicts
        
        # Get summaries
        prefix = f"summaries/{pr_id}/"
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        for blob in blobs:
            try:
                content = blob.download_as_text()
                summary["summaries"].append(json.loads(content))
            except Exception as e:
                logger.error(f"Error reading summary blob {blob.name}: {str(e)}")
        
        # Get validation logs
        prefix = f"validation/{pr_id}/"
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        for blob in blobs:
            try:
                content = blob.download_as_text()
                summary["validation"].append(json.loads(content))
            except Exception as e:
                logger.error(f"Error reading validation blob {blob.name}: {str(e)}")
        
        # Get diffs
        prefix = f"diffs/{pr_id}/"
        blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
        for blob in blobs:
            try:
                content = blob.download_as_text()
                summary["diffs"].append({
                    "name": blob.name,
                    "size": blob.size,
                    "created": blob.time_created,
                    "content": content
                })
            except Exception as e:
                logger.error(f"Error reading diff blob {blob.name}: {str(e)}")
        
        return summary
    
    def cleanup_old_files(self, days_old: int = 30):
        """Clean up files older than specified days."""
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        deleted_count = 0
        
        for blob in self.client.list_blobs(self.bucket_name):
            if blob.time_created and blob.time_created.replace(tzinfo=None) < cutoff_date:
                try:
                    blob.delete()
                    deleted_count += 1
                    logger.info(f"Deleted old file: {blob.name}")
                except Exception as e:
                    logger.error(f"Error deleting {blob.name}: {str(e)}")
        
        logger.info(f"Cleanup completed. Deleted {deleted_count} files older than {days_old} days")
        return deleted_count
