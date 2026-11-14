import os
import sys

from scripts.setup import setup_database


def main() -> None:
    setup_database()
    command = sys.argv[1:] or ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
