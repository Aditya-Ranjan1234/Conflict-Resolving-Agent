import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
import os

class AIResolver:
    def __init__(self, project_id: str, location: str = "us-central1", model_name: str = "gemini-2.5-flash-lite"):
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        
        # Initialize Vertex AI
        vertexai.init(project=self.project_id, location=self.location)
        self.model = GenerativeModel(self.model_name)

    def resolve_conflict(self, file_path: str, conflict_content: str, surrounding_context: str = "") -> str:
        """
        Uses Gemini to resolve a Git merge conflict.
        """
        prompt = f"""
        You are a senior software engineer specialized in resolving complex Git merge conflicts.
        
        File: {file_path}
        
        The file has merge conflicts marked with <<<<<<<, =======, and >>>>>>>.
        
        Your task is to:
        1. Understand the intent of both changes.
        2. Merge them intelligently, preserving functionality from both sides if applicable.
        3. Ensure the code is syntactically correct and follows common best practices.
        4. Return ONLY the final resolved file content, without any explanations, markdown code blocks, or additional text.
        
        {surrounding_context if surrounding_context else ""}
        
        CONFLICT CONTENT:
        {conflict_content}
        
        FINAL RESOLVED CONTENT:
        """
        
        generation_config = GenerationConfig(
            temperature=0.1,
            top_p=0.95,
            candidate_count=1,
            max_output_tokens=8192,
        )
        
        response = self.model.generate_content(
            prompt,
            generation_config=generation_config,
        )
        
        # Clean up response: remove markdown backticks if present
        resolved_content = response.text.strip()
        if resolved_content.startswith("```"):
            # Remove first and last lines (the backticks)
            lines = resolved_content.splitlines()
            if len(lines) > 2:
                resolved_content = "\n".join(lines[1:-1])
        
        return resolved_content
