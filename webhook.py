import os
import uvicorn
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv
from observability import instrument_fastapi

load_dotenv(override=True)
app = FastAPI(title="Webhook")
instrument_fastapi(app)
WEBHOOK_TOKEN = os.getenv("TOKEN")

@app.post("/a2a/webhook")
async def webhook(
    request: Request,
    x_a2a_notification_token: str | None = Header(default=None)
):
    # Validation Webhook
    if x_a2a_notification_token != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401)

    payload = await request.json()
    
    print("A2A Push Notification")
    print(payload)
    return {"status": "received"}

if __name__ == "__main__":
    uvicorn.run(app=app, host="127.0.0.1", port=8003)