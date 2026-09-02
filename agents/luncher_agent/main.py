import os
import uvicorn

port = int(os.getenv("PORT", 8080))
os.environ["PORT"] = str(port)

if __name__ == "__main__":
    print(f"[Luncher Agent] Starting Luncher Orchestrator server on port {port}...")
    uvicorn.run(
        "app.fast_api_app:app",
        host="0.0.0.0",
        port=port,
        reload=True,
    )

