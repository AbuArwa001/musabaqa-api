import uvicorn
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    env = os.environ.get("ENVIRONMENT", "development")
    
    # Enable hot-reloading for development environment
    reload = env.lower() == "development"

    print(f"Starting Musabaqa API on {host}:{port} (Reload: {reload})")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=reload,
        proxy_headers=True,  # Useful when running behind Nginx/reverse proxy on server
        forwarded_allow_ips="*"
    )
