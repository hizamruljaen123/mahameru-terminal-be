import abc
import asyncio
import subprocess
import tempfile
import os
import time
import base64
import shutil
from typing import Dict, Any, Optional

class BaseExecutor(abc.ABC):
    """Abstract base class for code executors."""
    
    @abc.abstractmethod
    def get_extension(self) -> str:
        pass
    
    @abc.abstractmethod
    def get_command(self, file_path: str) -> list:
        pass

    async def execute(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute the given code in a dedicated sandbox and return results."""
        start_time = time.time()
        
        # Create a unique sandbox directory for THIS execution
        # This prevents collisions and ensures we only capture images from this run
        root_sandbox = os.path.abspath("sandbox")
        os.makedirs(root_sandbox, exist_ok=True)
        sandbox_dir = tempfile.mkdtemp(dir=root_sandbox)
        
        # Create the script file inside the unique sandbox
        temp_path = os.path.join(sandbox_dir, f"script{self.get_extension()}")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(code)
            
        try:
            cmd = self.get_command(temp_path)
            
            # Security: Sanitize environment variables
            safe_env = {
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                "TEMP": sandbox_dir,
                "TMP": sandbox_dir,
                "PYTHONPATH": os.path.abspath("."),
                "PYTHONIOENCODING": "utf-8",
                "NODE_ICU_DATA": "",
                "LANG": "en_US.UTF-8",
                "HOME": sandbox_dir,
                "USERPROFILE": sandbox_dir,
                "MPLCONFIGDIR": sandbox_dir,
            }
            
            # Run in subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=safe_env,
                cwd=sandbox_dir
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                exit_code = process.returncode
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except:
                    pass
                return {
                    "stdout": "",
                    "stderr": f"Execution timed out after {timeout} seconds",
                    "exit_code": -1,
                    "duration_ms": round((time.time() - start_time) * 1000, 2),
                    "images": []
                }
            
            duration_ms = round((time.time() - start_time) * 1000, 2)
            
            # Capture any generated images
            images = []
            try:
                # Sort files to ensure predictable behavior (e.g., plot_1, plot_2)
                files = sorted([f for f in os.listdir(sandbox_dir) if f.lower().endswith(".png")])
                if files:
                    # Only take the LAST one to avoid duplicates if user saves manually AND plt.show() is called
                    last_file = files[-1]
                    file_path = os.path.join(sandbox_dir, last_file)
                    with open(file_path, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode("utf-8")
                        images.append(f"data:image/png;base64,{img_data}")
            except Exception as e:
                print(f"Error capturing images: {e}")

            return {
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "exit_code": exit_code if exit_code is not None else 0,
                "duration_ms": duration_ms,
                "images": images
            }
            
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"System Error: {str(e)}",
                "exit_code": 1,
                "duration_ms": round((time.time() - start_time) * 1000, 2),
                "images": []
            }
        finally:
            # Clean up the entire unique sandbox directory
            try:
                shutil.rmtree(sandbox_dir)
            except:
                pass
