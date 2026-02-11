import httpx
from .config import settings

class EchobClient:
    def __init__(self):
        self.base_url = settings.ECHOB_API_URL
        self.api_key = settings.ECHOB_API_KEY
        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    async def send_text(self, session: str, chat_id: str, text: str):
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/api/sendText"
            payload = {
                "session": session,
                "chatId": chat_id,
                "text": text
            }
            response = await client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def start_typing(self, session: str, chat_id: str):
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/api/startTyping"
            payload = {
                "session": session,
                "chatId": chat_id
            }
            # Ignore errors for typing indicators as they are non-critical
            try:
                await client.post(url, json=payload, headers=self.headers)
            except:
                pass

    async def stop_typing(self, session: str, chat_id: str):
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/api/stopTyping"
            payload = {
                "session": session,
                "chatId": chat_id
            }
            try:
                await client.post(url, json=payload, headers=self.headers)
            except:
                pass

echob_client = EchobClient()
