from .base import BaseExecutor
import shutil

class NodeExecutor(BaseExecutor):
    """
    Node.js code executor.
    Security:
    - Injects preamble to disable 'child_process' and dangerous 'fs' write operations
    """
    
    def get_extension(self) -> str:
        return ".js"
    
    def get_command(self, file_path: str) -> list:
        node_path = shutil.which("node")
        if not node_path:
            raise RuntimeError("Node.js is not installed")
        return [node_path, file_path]

    async def execute(self, code: str, timeout: int = 30) -> dict:
        preamble = """
// Surgical security for Node.js
const child_process = require('child_process');
const fs = require('fs');

const restricted = () => { throw new Error("This operation is restricted in this environment."); };

// Block execution
child_process.exec = restricted;
child_process.execSync = restricted;
child_process.spawn = restricted;
child_process.spawnSync = restricted;
child_process.fork = restricted;

// Block dangerous writes
fs.writeFileSync = restricted;
fs.writeFile = restricted;
fs.unlinkSync = restricted;
fs.rmdirSync = restricted;
fs.rmSync = restricted;
fs.renameSync = restricted;

// User Code:
"""
        full_code = preamble + code
        return await super().execute(full_code, timeout=timeout)
