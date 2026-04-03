import sys
import os
from pathlib import Path

# Add project root to sys.path to allow imports from root-level modules
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from main import app

def main():
    import uvicorn
    # Import main here to avoid issues with path during script execution
    uvicorn.run("main:app", host="0.0.0.0", port=7860, reload=False)

if __name__ == "__main__":
    main()
