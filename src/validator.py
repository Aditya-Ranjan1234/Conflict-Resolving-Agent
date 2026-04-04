import subprocess
import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class Validator:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        logger.info(f"Initializing Validator for repository: {repo_path}")

    def run_validation(self, command: str = "pytest") -> Tuple[bool, str]:
        """
        Runs a validation command (e.g., tests, linting).
        Returns (success: bool, output: str).
        """
        logger.info(f"Running validation command: {command}")
        
        try:
            # Run the command in the repo directory
            logger.info(f"Executing command in {self.repo_path}")
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info(f"Validation command succeeded with return code: {result.returncode}")
            logger.info(f"Stdout length: {len(result.stdout)} characters")
            if result.stderr:
                logger.warning(f"Stderr length: {len(result.stderr)} characters")
            
            return True, result.stdout
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Validation command failed with return code: {e.returncode}")
            logger.error(f"Stdout: {e.stdout}")
            logger.error(f"Stderr: {e.stderr}")
            return False, e.stdout + e.stderr
        except Exception as e:
            logger.error(f"Unexpected error during validation: {str(e)}")
            logger.exception("Full validation error:")
            return False, str(e)

    def detect_test_command(self) -> str:
        """
        Guesses the test command based on the repository structure.
        """
        logger.info(f"Detecting test command for repository: {self.repo_path}")
        
        try:
            files = os.listdir(self.repo_path)
            logger.info(f"Found files in repository: {files}")
            
            if "requirements.txt" in files or "setup.py" in files or "pyproject.toml" in files:
                logger.info("Detected Python project, using pytest")
                return "pytest"
            elif "package.json" in files:
                logger.info("Detected Node.js project, using npm test")
                return "npm test"
            elif "go.mod" in files:
                logger.info("Detected Go project, using go test")
                return "go test ./..."
            elif "pom.xml" in files:
                logger.info("Detected Maven project, using mvn test")
                return "mvn test"
            
            logger.warning("No recognized test framework found, defaulting to ls -R")
            return "ls -R" # Default to listing files if no test framework found
            
        except Exception as e:
            logger.error(f"Error detecting test command: {str(e)}")
            return "ls -R"  # Safe default
