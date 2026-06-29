"""Root-level entry point for the packaged app.

PyInstaller runs the entry script as ``__main__`` with no parent package, which
breaks relative imports. Keeping this launcher at the project root (so ``import
devdeck`` resolves) lets the package use normal relative imports internally.
"""
from devdeck.main import main

if __name__ == "__main__":
    raise SystemExit(main())
