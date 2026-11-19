"""Allow `python -m repurpose ...`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
