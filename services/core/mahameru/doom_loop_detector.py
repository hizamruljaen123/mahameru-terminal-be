import hashlib
import json
from typing import List, Tuple, Any, Dict

class DoomLoopDetector:
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.recent_calls: List[Tuple[str, str]] = []  # [(tool_name, params_hash), ...]
    
    def _hash_params(self, params: Any) -> str:
        if isinstance(params, str):
            try:
                # Try to parse as JSON to ensure consistent hashing if it's a JSON string
                parsed = json.loads(params)
                params_str = json.dumps(parsed, sort_keys=True)
            except json.JSONDecodeError:
                params_str = params
        else:
            params_str = json.dumps(params, sort_keys=True)
        return hashlib.md5(params_str.encode('utf-8')).hexdigest()

    def check(self, tool_name: str, params: Any) -> bool:
        """
        Records a tool call and returns True if a doom loop is detected.
        A doom loop is when the exact same tool with the exact same parameters
        is called `self.threshold` times in a row.
        """
        params_hash = self._hash_params(params)
        self.recent_calls.append((tool_name, params_hash))
        
        # Keep only the last `threshold` calls to save memory
        if len(self.recent_calls) > self.threshold:
            self.recent_calls.pop(0)
            
        if len(self.recent_calls) == self.threshold:
            first_call = self.recent_calls[0]
            # Check if all calls in the window are identical
            if all(call == first_call for call in self.recent_calls):
                return True
                
        return False
        
    def reset(self):
        self.recent_calls.clear()
