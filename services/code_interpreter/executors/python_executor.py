import sys
import os
import tempfile
from .base import BaseExecutor

class PythonExecutor(BaseExecutor):
    """
    Python code executor.
    Security:
    - Uses -I (Isolated mode)
    - Path-aware security: Allows file operations within the sandbox
    - Blocks shell execution entirely
    """
    
    def get_extension(self) -> str:
        return ".py"
    
    def get_command(self, file_path: str) -> list:
        return [sys.executable, "-I", file_path]

    async def execute(self, code: str, timeout: int = 30) -> dict:
        preamble = """
import sys
import os
import subprocess
import io

# Force UTF-8 for stdout/stderr to fix Windows/Anaconda encoding issues
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Store originals
_orig_os_system = os.system
_orig_os_popen = os.popen
_orig_subprocess_popen = subprocess.Popen
_orig_os_unlink = os.unlink
_orig_os_remove = os.remove
_orig_os_rmdir = os.rmdir
_orig_subprocess_run = subprocess.run
_orig_subprocess_call = subprocess.call
_orig_subprocess_check_call = subprocess.check_call
_orig_subprocess_check_output = subprocess.check_output

def restricted_shell(*args, **kwargs):
    raise RuntimeError("Shell execution is restricted in this environment.")

def path_aware_op(orig_func):
    def wrapper(path, *args, **kwargs):
        try:
            abs_path = os.path.abspath(str(path))
            # Get current sandbox dir (which is the CWD)
            cwd = os.getcwd()
            if not abs_path.startswith(cwd):
                raise RuntimeError(f"Access to path outside sandbox is restricted: {path}")
            return orig_func(path, *args, **kwargs)
        except Exception as e:
            if isinstance(e, RuntimeError): raise
            return orig_func(path, *args, **kwargs)
    return wrapper

# Block shell entirely
os.system = restricted_shell
os.popen = restricted_shell
# Block shell execution while allowing inheritance (required for asyncio on Windows)
class RestrictedPopen(_orig_subprocess_popen):
    def __init__(self, *args, **kwargs):
        # Allow internal asyncio/subprocess usage if not a string command (shell)
        cmd = args[0] if args else kwargs.get("args")
        is_shell = kwargs.get("shell", False)
        
        # Security: Allow only 'ver' (needed by platform.py)
        is_safe = False
        if isinstance(cmd, str) and cmd.strip().lower() == 'ver':
            is_safe = True
        elif isinstance(cmd, (list, tuple)) and len(cmd) == 1 and cmd[0].lower() == 'ver':
            is_safe = True
            
        if (isinstance(cmd, str) or is_shell) and not is_safe:
             raise RuntimeError("Shell execution is restricted in this environment.")
        super().__init__(*args, **kwargs)

subprocess.Popen = RestrictedPopen
subprocess.run = _orig_subprocess_run
subprocess.call = _orig_subprocess_call
subprocess.check_call = _orig_subprocess_check_call
subprocess.check_output = _orig_subprocess_check_output

# Make file deletions path-aware (allows matplotlib to manage its cache in sandbox)
os.unlink = path_aware_op(_orig_os_unlink)
os.remove = path_aware_op(_orig_os_remove)
os.rmdir = path_aware_op(_orig_os_rmdir)

# Matplotlib Support
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    
    def custom_show(*args, **kwargs):
        count = len([f for f in os.listdir() if f.startswith('plot_') and f.endswith('.png')])
        plt.savefig(f'plot_{count+1}.png', bbox_inches='tight', dpi=100)
        plt.close()
    
    plt.show = custom_show
except ImportError:
    pass

# User Code:
"""
        full_code = preamble + code
        return await super().execute(full_code, timeout=timeout)
