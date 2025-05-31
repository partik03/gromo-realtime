from fastapi import WebSocket
import asyncio
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self):
        self.streams = {}  # For media streams
        self.frontend_clients = {}  # For frontend clients
        self.active_streams = set()  # Track active streams
        self.last_heartbeat = {}  # Track last heartbeat time for each connection
        self.heartbeat_interval = 10  # Send heartbeat every 10 seconds (reduced from 20)
        self.heartbeat_timeout = 30  # Consider connection dead after 30 seconds (reduced from 40)
        self.connection_tasks = {}  # Store heartbeat tasks for cleanup

    def add_stream(self, stream_sid: str, websocket: WebSocket):
        self.streams[stream_sid] = websocket
        self.active_streams.add(stream_sid)
        self.last_heartbeat[stream_sid] = time.time()
        logger.info(f"Added stream: {stream_sid}")

    def add_frontend_client(self, client_id: str, websocket: WebSocket):
        self.frontend_clients[client_id] = websocket
        self.last_heartbeat[client_id] = time.time()
        logger.info(f"Added frontend client: {client_id}")

    def remove_stream(self, stream_sid: str):
        if stream_sid in self.streams:
            del self.streams[stream_sid]
            self.active_streams.remove(stream_sid)
            if stream_sid in self.last_heartbeat:
                del self.last_heartbeat[stream_sid]
            if stream_sid in self.connection_tasks:
                self.connection_tasks[stream_sid].cancel()
                del self.connection_tasks[stream_sid]
            logger.info(f"Removed stream: {stream_sid}")

    def remove_frontend_client(self, client_id: str):
        if client_id in self.frontend_clients:
            del self.frontend_clients[client_id]
            if client_id in self.last_heartbeat:
                del self.last_heartbeat[client_id]
            if client_id in self.connection_tasks:
                self.connection_tasks[client_id].cancel()
                del self.connection_tasks[client_id]
            logger.info(f"Removed frontend client: {client_id}")

    def update_heartbeat(self, connection_id: str):
        """Update the last heartbeat timestamp for a connection"""
        self.last_heartbeat[connection_id] = time.time()
        logger.debug(f"Updated heartbeat for {connection_id}")

    async def send_heartbeat(self, websocket: WebSocket, connection_id: str):
        """Send a heartbeat message to the specified connection"""
        try:
            heartbeat_message = {
                "type": "heartbeat",
                "timestamp": time.time()
            }
            await websocket.send_json(heartbeat_message)
            self.update_heartbeat(connection_id)
            logger.debug(f"Sent heartbeat to {connection_id}")
        except Exception as e:
            logger.error(f"Error sending heartbeat to {connection_id}: {type(e).__name__}: {e}")

            logger.error(f"Error sending heartbeat to {connection_id}: {e}")
            if connection_id in self.streams:
                self.remove_stream(connection_id)
            elif connection_id in self.frontend_clients:
                self.remove_frontend_client(connection_id)

    async def monitor_connection(self, websocket: WebSocket, connection_id: str):
        """Monitor connection health and send heartbeats"""
        while True:
            try:
                # Check if connection is still healthy
                if not self.check_connection_health(connection_id):
                    logger.warning(f"Connection {connection_id} failed health check")
                    break

                # Send heartbeat
                await self.send_heartbeat(websocket, connection_id)
                
                # Wait for next heartbeat
                await asyncio.sleep(self.heartbeat_interval)
                
            except asyncio.CancelledError:
                logger.info(f"Heartbeat monitoring cancelled for {connection_id}")
                break
            except Exception as e:
                logger.error(f"Error in connection monitoring for {connection_id}: {e}")
                break

    async def start_heartbeat(self, websocket: WebSocket, connection_id: str):
        """Start the heartbeat monitoring for a connection"""
        # Cancel existing task if any
        if connection_id in self.connection_tasks:
            self.connection_tasks[connection_id].cancel()
        
        # Create new monitoring task
        task = asyncio.create_task(self.monitor_connection(websocket, connection_id))
        self.connection_tasks[connection_id] = task
        
        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"Heartbeat task cancelled for {connection_id}")
        except Exception as e:
            logger.error(f"Heartbeat task error for {connection_id}: {e}")
        finally:
            if connection_id in self.connection_tasks:
                del self.connection_tasks[connection_id]

    def check_connection_health(self, connection_id: str) -> bool:
        """Check if a connection is healthy based on its last heartbeat"""
        if connection_id not in self.last_heartbeat:
            return False
        time_since_last_heartbeat = time.time() - self.last_heartbeat[connection_id]
        is_healthy = time_since_last_heartbeat < self.heartbeat_timeout
        if not is_healthy:
            logger.warning(f"Connection {connection_id} unhealthy: {time_since_last_heartbeat:.2f}s since last heartbeat")
        return is_healthy

    def get_active_frontend_client(self):
        """Get the first active frontend client"""
        if self.frontend_clients:
            return next(iter(self.frontend_clients.keys()))
        return None

    async def send_to_frontend(self, message: dict):
        """Send a message to all frontend clients"""
        clients = list(self.frontend_clients.items())
        for client_id, websocket in clients:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to frontend client {client_id}: {e}")
                self.remove_frontend_client(client_id)

# Create a single instance to be used across the application
websocket_manager = WebSocketManager() 