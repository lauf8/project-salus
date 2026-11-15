import sys

from scripts.setup import setup_database
from scripts.sync_mission_risks import main


if __name__ == '__main__':
    setup_database()
    sys.argv.append('--watch')
    main()
