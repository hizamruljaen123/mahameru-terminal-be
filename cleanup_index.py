import os
import re

path = "/root/project/mahameru-terminal-fe/dist/index.html"
if os.path.exists(path):
    with open(path, "r") as f:
        content = f.read()
    
    # Remove CSP meta tag (handles multiline)
    content = re.sub(r"<meta http-equiv=\"Content-Security-Policy\".*?>", "", content, flags=re.DOTALL)
    
    with open(path, "w") as f:
        f.write(content)
    print("Successfully cleaned index.html")
else:
    print("index.html not found at " + path)
