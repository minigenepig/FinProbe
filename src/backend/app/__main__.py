from .main import app

if __name__ == "__main__":
    import uvicorn
    from .config import get_settings

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)