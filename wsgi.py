import os
import sys

# Ensure the project directory is on the Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import the create_app function from main.py
from main import create_app

# Create the Flask app instance
app = create_app()

# Optional: run locally with `python wsgi.py`
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
