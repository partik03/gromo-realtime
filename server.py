#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import json

import uvicorn
from bot import run_bot
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse,Response
import base64
import audioop
import wave
from utils.helpers import create_sip_room
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/")
async def start_call():
    print("POST TwiML")
    return HTMLResponse(content=open("templates/streams.xml").read(), media_type="application/xml")


@app.get("/")
def func():
    return "Hello World"


@app.post("/call")
async def twilio_voice(request: Request):
    print("🟢 Twilio voice request received")

    twiml = """
    <Response>
        <Start>
            <Stream url="wss://f9bc-103-98-23-90.ngrok-free.app/ws" />
        </Start>
        <Say>AI Assistant joined</Say>
        <Pause length="60"/>
    </Response>
    """

    return Response(content=twiml, media_type="text/xml")

# @app.websocket("/ws")
# async def websocket_endpoint(websocket: WebSocket):
#     await websocket.accept()
#     print("WebSocket connection accepted")

#     wf = None  # Will hold the WAV file handler

#     try:
#         while True:
#             msg = await websocket.receive_text()
#             data = json.loads(msg)
#             event_type = data.get("event")

#             # Handle 'start' event
#             if event_type == "start":
#                 stream_sid = data.get("streamSid", "unknown")
#                 print(f"🔵 Stream started: {stream_sid}")

#                 # Open WAV file
#                 wf = wave.open(f"{stream_sid}.wav", 'wb')
#                 wf.setnchannels(1)          # mono
#                 wf.setsampwidth(2)          # 16-bit PCM
#                 wf.setframerate(8000)       # 8 kHz

#             # Handle 'media' event
#             elif event_type == "media":
#                 if wf is not None:
#                     b64payload = data["media"]["payload"]
#                     mulaw_audio = base64.b64decode(b64payload)
#                     # pcm_audio = audioop.ulaw2lin(mulaw_audio, 2)
#                     wf.writeframes(mulaw_audio)

#             # Handle 'mark' event (optional)
#             elif event_type == "mark":
#                 print(f"📍 Mark received: {data.get('mark', {}).get('name')}")

#             # Handle 'stop' event
#             elif event_type == "stop":
#                 print(f"🔴 Stream stopped: {data.get('streamSid')}")
#                 if wf:
#                     wf.close()
#                     wf = None
#                     print("✅ Audio file saved.")

#             else:
#                 print(f"⚠️ Unknown event: {event_type}", flush=True)

#     except Exception as e:
#         print("❌ WebSocket closed or error occurred:", e)
#     finally:
#         if wf:
#             wf.close()


# @app.websocket("/ws")
# async def voice_websocket_endpoint(websocket: WebSocket):
#     try:
#         print(f"New WebSocket connection for call UUID:............. ")
#         await websocket.accept()
#         start_data = websocket.iter_text()
#         await start_data.__anext__()
#         call_data = json.loads(await start_data.__anext__())
#         print(call_data, flush=True)
#         # stream_sid = call_data["streamSid"]
#         stream_sid = call_data["stream_sid"]
#         print("WebSocket connection accepted")
#         await run_bot(websocket, stream_sid)
#     except Exception as e:
#         print(f"WebSocket error: {e}")
#     finally:
#         # Ensure proper cleanup
#         try:
#             await websocket.close()
#         except:
#             pass



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await websocket.accept()
        print("WebSocket connection accepted")
        start_data = websocket.iter_text()
        await start_data.__anext__()
        call_data = json.loads(await start_data.__anext__())
        print(call_data, flush=True)
        # stream_sid = call_data["start"]["stream_sid"]
        stream_sid = call_data["stream_sid"]
        # room_url, token, sip_endpoint = await create_sip_room()
        # print(f"Room URL: {room_url}, Token: {token}, SIP Endpoint: {sip_endpoint}")
        # await run_bot(websocket, room_url, token, sip_endpoint)
        await run_bot(websocket, stream_sid)
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipecat Twilio Chatbot Server")
    parser.add_argument(
        "-t", "--test", action="store_true", default=False, help="set the server in testing mode"
    )
    args, _ = parser.parse_known_args()

    app.state.testing = args.test

    uvicorn.run(app, host="0.0.0.0", port=8000)
    # await run_bot(websocket, stream_sid, call_sid, app.state.testing)
    # await run_bot(websocket, app.state.testing)