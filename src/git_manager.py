import os
import shutil
from git import Repo, GitCommandError
from typing import List, Dict, Tuple

class GitManager:
    def __init__(self, base_path: str = "temp/repos"):
        self.base_path = base_path
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)

    def clone_repo(self, repo_url: str, repo_name: str, token: str = None) -> str:
        """Clones a repository using an optional GitHub token."""
        if token:
            # Inject token into URL: https://<token>@github.com/user/repo.git
            repo_url = repo_url.replace("https://", f"https://{token}@")
        
        repo_path = os.path.join(self.base_path, repo_name)
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
        
        Repo.clone_from(repo_url, repo_path)
        
        # Configure git identity for the repository
        repo = Repo(repo_path)
        with repo.config_writer() as cw:
            cw.set_value("user", "name", "Conflict Resolving Agent")
            cw.set_value("user", "email", "agent@conflict-resolver.ai")
            
        return repo_path

    def attempt_merge(self, repo_path: str, source_branch: str, target_branch: str) -> List[str]:
        """
        Attempts to merge source_branch into target_branch.
        Returns a list of files with conflicts.
        """
        repo = Repo(repo_path)
        
        # Ensure we have the latest from origin
        repo.remotes.origin.fetch()
        
        # Create a local tracking branch for the source if it doesn't exist
        try:
            repo.git.checkout("-b", source_branch, f"origin/{source_branch}")
        except GitCommandError:
            # If it already exists, just switch to it and pull
            repo.git.checkout(source_branch)
            repo.git.pull("origin", source_branch)

        # Checkout target branch (base of the PR)
        repo.git.checkout(target_branch)
        
        try:
            # Merge the local source branch
            repo.git.merge(source_branch)
            return []  # No conflicts
        except GitCommandError as e:
            if "CONFLICT" in str(e):
                # Get list of unmerged files (those with conflicts)
                unmerged_files = repo.git.diff("--name-only", "--diff-filter=U").splitlines()
                return unmerged_files
            else:
                raise e

    def get_conflict_context(self, repo_path: str, file_path: str) -> str:
        """Reads the content of a file with conflict markers."""
        full_path = os.path.join(repo_path, file_path)
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()

    def apply_resolution(self, repo_path: str, file_path: str, resolved_content: str):
        """Overwrites the conflicting file with the resolved content."""
        full_path = os.path.join(repo_path, file_path)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(resolved_content)
        
        repo = Repo(repo_path)
        # Using repo.git.add is more robust for resolving unmerged states
        repo.git.add(file_path)

    def commit_and_push(self, repo_path: str, branch_name: str, message: str):
        """Commits and pushes the resolved changes."""
        repo = Repo(repo_path)
        # Using repo.git.commit is more robust during a merge state
        repo.git.commit("-m", message)
        # Push using the branch name correctly to origin
        repo.git.push("origin", branch_name)

    def cleanup(self, repo_path: str):
        """Removes the cloned repository."""
        if os.path.exists(repo_path):
            shutil.rmtree(repo_path)
