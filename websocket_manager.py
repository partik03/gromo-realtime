from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        self.streams = {}  # For media streams
        self.frontend_clients = {}  # For frontend clients
        self.active_streams = set()  # Track active streams

    def add_stream(self, stream_sid: str, websocket: WebSocket):
        self.streams[stream_sid] = websocket
        self.active_streams.add(stream_sid)

    def add_frontend_client(self, client_id: str, websocket: WebSocket):
        self.frontend_clients[client_id] = websocket

    def remove_stream(self, stream_sid: str):
        if stream_sid in self.streams:
            del self.streams[stream_sid]
            self.active_streams.remove(stream_sid)

    def remove_frontend_client(self, client_id: str):
        if client_id in self.frontend_clients:
            del self.frontend_clients[client_id]

    def get_active_frontend_client(self):
        # Get the first active frontend client
        # You might want to implement a more sophisticated selection logic
        if self.frontend_clients:
            return next(iter(self.frontend_clients.keys()))
        return None

    async def send_to_frontend(self, message: dict):
        # Create a copy of items to safely iterate over
        clients = list(self.frontend_clients.items())
        # Send to all connected frontend clients
        for client_id, websocket in clients:
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"Error sending to frontend client {client_id}: {e}")
                self.remove_frontend_client(client_id)

# Create a single instance to be used across the application
websocket_manager = WebSocketManager() 