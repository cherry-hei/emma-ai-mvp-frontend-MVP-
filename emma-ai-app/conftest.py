import pathlib
import sys

# Make emma_core importable when running pytest from the app root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
