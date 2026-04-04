import os
import logging
import shutil
from urllib.parse import quote
from git import Repo, GitCommandError
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

class GitManager:
    def __init__(self, base_path: str = "temp/repos"):
        self.base_path = base_path
        logger.info(f"Initializing GitManager with base_path: {base_path}")
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)
            logger.info(f"Created base directory: {self.base_path}")
        else:
            logger.info(f"Base directory already exists: {self.base_path}")

    def clone_repo(self, repo_url: str, repo_name: str, token: str = None) -> str:
        """Clones a repository using an optional GitHub token."""
        logger.info(f"Starting clone of {repo_name} from {repo_url}")
        
        if token:
            # Use proper GitHub token format with URL encoding: https://x-access-token:<encoded-token>@github.com/user/repo.git
            if repo_url.startswith("https://"):
                encoded_token = quote(token, safe="")
                repo_url = f"https://x-access-token:{encoded_token}@{repo_url[8:]}"  # Remove https:// and add token
            logger.info("Using token for authentication with x-access-token format (URL encoded)")
        
        repo_path = os.path.join(self.base_path, repo_name)
        logger.info(f"Target clone path: {repo_path}")
        
        if os.path.exists(repo_path):
            logger.info(f"Removing existing repository at {repo_path}")
            shutil.rmtree(repo_path)
        
        try:
            logger.info("Executing git clone...")
            Repo.clone_from(repo_url, repo_path)
            logger.info(f"Successfully cloned repository to {repo_path}")
        except Exception as e:
            logger.error(f"Failed to clone repository: {str(e)}")
            raise
        
        # Configure git identity for the repository
        logger.info("Configuring git identity...")
        repo = Repo(repo_path)
        try:
            with repo.config_writer() as cw:
                cw.set_value("user", "name", "Conflict Resolving Agent")
                cw.set_value("user", "email", "agent@conflict-resolver.ai")
            logger.info("Git identity configured successfully")
        except Exception as e:
            logger.error(f"Failed to configure git identity: {str(e)}")
            raise
            
        return repo_path

    def attempt_merge(self, repo_path: str, source_branch: str, target_branch: str) -> List[str]:
        """
        Attempts to merge source_branch into target_branch.
        Returns a list of files with conflicts.
        """
        logger.info(f"Attempting merge: {source_branch} -> {target_branch}")
        repo = Repo(repo_path)
        
        try:
            # Ensure we have the latest from origin
            logger.info("Fetching latest changes from origin...")
            repo.remotes.origin.fetch()
            logger.info("Fetch completed successfully")
        except Exception as e:
            logger.error(f"Failed to fetch from origin: {str(e)}")
            raise
        
        # Create a local tracking branch for the source if it doesn't exist
        try:
            logger.info(f"Creating local tracking branch for {source_branch}...")
            repo.git.checkout("-b", source_branch, f"origin/{source_branch}")
            logger.info(f"Created local branch {source_branch}")
        except GitCommandError as e:
            logger.info(f"Branch {source_branch} already exists, switching and pulling...")
            try:
                repo.git.checkout(source_branch)
                repo.git.pull("origin", source_branch)
                logger.info(f"Switched to and updated {source_branch}")
            except Exception as pull_error:
                logger.error(f"Failed to update {source_branch}: {str(pull_error)}")
                raise

        # Checkout target branch (base of the PR)
        logger.info(f"Switching to target branch: {target_branch}")
        try:
            repo.git.checkout(target_branch)
            logger.info(f"Switched to target branch: {target_branch}")
        except Exception as e:
            logger.error(f"Failed to checkout target branch {target_branch}: {str(e)}")
            raise
        
        try:
            # Merge the local source branch
            logger.info(f"Attempting merge of {source_branch} into {target_branch}...")
            repo.git.merge(source_branch)
            logger.info("Merge completed successfully with no conflicts")
            return []  # No conflicts
        except GitCommandError as e:
            if "CONFLICT" in str(e):
                logger.warning(f"Merge conflicts detected: {str(e)}")
                try:
                    # Get list of unmerged files (those with conflicts)
                    unmerged_files = repo.git.diff("--name-only", "--diff-filter=U").splitlines()
                    logger.info(f"Found {len(unmerged_files)} files with conflicts: {unmerged_files}")
                    return unmerged_files
                except Exception as list_error:
                    logger.error(f"Failed to list conflicted files: {str(list_error)}")
                    raise
            else:
                logger.error(f"Merge failed with non-conflict error: {str(e)}")
                raise e

    def get_conflict_context(self, repo_path: str, file_path: str) -> str:
        """Reads the content of a file with conflict markers."""
        full_path = os.path.join(repo_path, file_path)
        logger.info(f"Reading conflict context from {full_path}")
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"Read {len(content)} characters from {file_path}")
            return content
        except Exception as e:
            logger.error(f"Failed to read conflict context from {file_path}: {str(e)}")
            raise

    def apply_resolution(self, repo_path: str, file_path: str, resolved_content: str):
        """Overwrites the conflicting file with the resolved content."""
        full_path = os.path.join(repo_path, file_path)
        logger.info(f"Applying resolution to {full_path} ({len(resolved_content)} chars)")
        
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(resolved_content)
            logger.info(f"Successfully wrote resolved content to {file_path}")
        except Exception as e:
            logger.error(f"Failed to write resolved content to {file_path}: {str(e)}")
            raise
        
        try:
            repo = Repo(repo_path)
            # Using repo.git.add is more robust for resolving unmerged states
            repo.git.add(file_path)
            logger.info(f"Successfully staged resolved file: {file_path}")
        except Exception as e:
            logger.error(f"Failed to stage resolved file {file_path}: {str(e)}")
            raise

    def commit_and_push(self, repo_path: str, branch_name: str, message: str, token: str = None):
        """Commits and pushes the resolved changes."""
        logger.info(f"Starting commit and push for branch: {branch_name}")
        logger.info(f"Commit message: {message}")
        
        repo = Repo(repo_path)
        try:
            # Check git status before commit
            status = repo.git.status()
            logger.info(f"Git status before commit: {status}")
            
            # Using repo.git.commit is more robust during a merge state
            logger.info("Attempting to commit changes...")
            repo.git.commit("-m", message)
            logger.info(f"Successfully committed changes with message: {message}")
            
            # Configure push URL with token if provided
            if token:
                logger.info("Configuring authentication for push...")
                # Use proper GitHub token format with URL encoding for push URL
                encoded_token = quote(token, safe="")
                auth_url = f"https://x-access-token:{encoded_token}@github.com/Aditya-Ranjan1234/Test-Conflict-Resolving-Agent.git"
                
                # Explicitly set the remote URL for both push and fetch
                repo.git.remote("set-url", "origin", auth_url)
                logger.info("Authentication configured for push with x-access-token format (URL encoded)")
            else:
                logger.warning("No token provided for push authentication")
            
            # Push using the correct branch - we're on main after merge, so push main
            logger.info(f"Pushing to origin/main...")
            repo.git.push("origin", "main")
            logger.info(f"Successfully pushed to branch: main")
            
        except GitCommandError as e:
            logger.error(f"Git command failed: {str(e)}")
            logger.error(f"Git status after failure: {repo.git.status() if repo else 'No repo'}")
            raise GitCommandError(f"Failed to commit and push: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during commit and push: {str(e)}")
            logger.exception("Full exception details:")
            raise

    def cleanup(self, repo_path: str):
        """Removes the cloned repository."""
        logger.info(f"Cleaning up repository at {repo_path}")
        try:
            if os.path.exists(repo_path):
                shutil.rmtree(repo_path)
                logger.info(f"Successfully removed repository at {repo_path}")
            else:
                logger.warning(f"Repository path does not exist for cleanup: {repo_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup repository at {repo_path}: {str(e)}")
