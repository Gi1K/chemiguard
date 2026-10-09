import os

import uvicorn

from . import config


if __name__ == '__main__':
    uvicorn.run('chemiguard.app:app', host='127.0.0.1', port=int(os.getenv('CHEMIGUARD_PORT', '8765')))
