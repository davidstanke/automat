import os
import uvicorn

port = int(os.getenv("PORT", 8081))
os.environ["PORT"] = str(port)

if __name__ == "__main__":
    print(f"[Strategy Agent] Starting Strategy Agent server on port {port}...")
    uvicorn.run(
        "app.fast_api_app:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )

