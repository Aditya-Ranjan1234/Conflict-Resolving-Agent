import subprocess
import os
from typing import Tuple

class Validator:
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def run_validation(self, command: str = "pytest") -> Tuple[bool, str]:
        """
        Runs a validation command (e.g., tests, linting).
        Returns (success: bool, output: str).
        """
        try:
            # Run the command in the repo directory
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            return False, e.stdout + e.stderr
        except Exception as e:
            return False, str(e)

    def detect_test_command(self) -> str:
        """
        Guesses the test command based on the repository structure.
        """
        files = os.listdir(self.repo_path)
        
        if "requirements.txt" in files or "setup.py" in files or "pyproject.toml" in files:
            return "pytest"
        elif "package.json" in files:
            return "npm test"
        elif "go.mod" in files:
            return "go test ./..."
        elif "pom.xml" in files:
            return "mvn test"
        
        return "ls -R" # Default to listing files if no test framework found
