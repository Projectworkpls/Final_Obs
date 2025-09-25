import os
import sys

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

from main import create_app   # CHANGED: from app → from main

# Create the Flask app
app = create_app()

if __name__ == "__main__":
    app.run()
