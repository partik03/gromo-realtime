#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

import argparse
import json
# import hypercorn
import uvicorn
from bot import run_bot
from fastapi import FastAPI, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse,Response
# import base64
# import audioop
# import wave
from websocket_manager import websocket_manager
from utils.helpers import create_sip_room
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.websocket_keepalive = True
app.websocket_ping_interval = 60.0  # Send ping every 20 seconds
app.websocket_ping_timeout = 600.0 


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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await websocket.accept()
        print("WebSocket connection accepted")
        # websocket.
        # Wait for initial message
        start_data = websocket.iter_text()
        print("🟢 Waiting for initial message", start_data)
        await start_data.__anext__()
        call_data = json.loads(await start_data.__anext__())
        print(f"Received connection data: {call_data}", flush=True)
        
        # Handle different types of connections
        if "stream_sid" in call_data:
            # This is the media stream connection
            stream_sid = call_data["stream_sid"]
            websocket_manager.add_stream(stream_sid, websocket)
            try:
                # Get active frontend client
                frontend_client_id = websocket_manager.get_active_frontend_client()
                # if frontend_client_id:
                await run_bot(websocket, stream_sid)
                # else:
                #     print("No active frontend client found")
            except Exception as e:
                print(f"Error in run_bot: {e}")
            finally:
                websocket_manager.remove_stream(stream_sid)
                
        elif "client_type" in call_data and call_data["client_type"] == "frontend":
            print("🟢 Frontend connection received", call_data)
            # This is the frontend connection
            client_id = call_data.get("client_id")
            if not client_id:
                print("No client_id provided for frontend client")
                return
                
            websocket_manager.add_frontend_client(client_id, websocket)
            
            try:
                while True:
                    try:
                        data = await websocket.receive_text()
                        print(f"Received message from frontend client {client_id}: {data}")
                    except:
                        print(f"Frontend client {client_id} disconnected")
                        break
            finally:
                websocket_manager.remove_frontend_client(client_id)
                
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        try:
            await websocket.close()
        except:
            pass

# if __name__ == "__main__":
#     import hypercorn.asyncio
#     import hypercorn.config
#     import asyncio
    
#     config = hypercorn.config.Config()
#     config.bind = ["0.0.0.0:8000"]
    
#     # CRITICAL: Set to None (not 0) to completely disable
#     config.websocket_ping_interval = 0
#     config.websocket_ping_timeout = 0
#     config.keep_alive_timeout = 0
    
#     # Disable all timeouts
#     config.graceful_timeout = 0
#     config.shutdown_timeout = 0
    
#     asyncio.run(hypercorn.asyncio.serve(app, config))

if __name__ == "__main__":
    try:
        uvicorn.run(
            "server:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            ws="websockets",
            ws_ping_interval=30.0,    # Disable ping
            ws_ping_timeout=60.0,     # Disable ping timeout
        )
    except TypeError:
            # Fallback for older Uvicorn versions
            print("WebSocket ping configuration not supported in this Uvicorn version")
            print("Consider upgrading Uvicorn or using Hypercorn")
            uvicorn.run(
                "main:app",
                host="0.0.0.0",
                port=8000,
                log_level="info"
            )




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




