from .base import BaseExecutor
import os
import shutil

class ShellExecutor(BaseExecutor):
    """Shell/Bash code executor."""
    
    def get_extension(self) -> str:
        # Detect OS for extension
        return ".sh" if os.name != 'nt' else ".bat"
    
    def get_command(self, file_path: str) -> list:
        if os.name == 'nt':
            # Windows CMD
            return ["cmd.exe", "/c", file_path]
        else:
            # Unix Bash
            bash_path = shutil.which("bash") or "/bin/sh"
            return [bash_path, file_path]
