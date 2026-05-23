import os

import uvicorn


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    from app.settings import APP_PORT

    port = APP_PORT
    reload = os.environ.get("RELOAD", "1").lower() in ("1", "true", "yes")
    trust_proxy = os.environ.get("TRUST_PROXY", "").lower() in ("1", "true", "yes")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        proxy_headers=trust_proxy,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "*"),
    )


if __name__ == "__main__":
    main()
