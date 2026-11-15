import sys

from scripts.predictive_worker import main
from scripts.setup import setup_database


if __name__ == '__main__':
    setup_database()
    sys.argv.append('--watch')
    main()
