import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("SECRET_KEY", "cle-de-test")
os.environ.setdefault("AI_PROVIDER", "mock")
