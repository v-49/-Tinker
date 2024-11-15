# ws_routes.py
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
ws_router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"connect：{websocket.client}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"disconnet：{websocket.client}")

    async def broadcast(self, message: dict):
        tasks = []
        for connection in self.active_connections:
            tasks.append(self._send_message(connection, message))
        await asyncio.gather(*tasks)

    async def _send_message(self, connection: WebSocket, message: dict):
        try:
            await connection.send_json(message)
            logger.info(f"message to {connection.client}。")
        except WebSocketDisconnect:
            self.disconnect(connection)

manager = ConnectionManager()

@ws_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await manager.connect(websocket)
        logger.info(f"ws connecting：{websocket.client}")
        while True:
            data = await websocket.receive_text()
            logger.info(f"{websocket.client}send：{data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"ws end：{websocket.client}")
    except Exception as e:
        logger.error(f"ws error：{e}")
