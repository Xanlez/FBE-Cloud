import os
import sys

import uvicorn


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "1010"))
    reload = os.environ.get("RELOAD", "0").lower() in ("1", "true", "yes")

    uvicorn.run("main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    # python manage.py  или  python manage.py runserver
    main()
