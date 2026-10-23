"""Development entry point:  python run.py"""
import os

from kubeassist import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("KUBEASSIST_HOST", "127.0.0.1"),
            port=int(os.environ.get("KUBEASSIST_PORT", "5000")))
