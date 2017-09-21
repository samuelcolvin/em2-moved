from em2.fallback import LogFallbackHandler


class TestFallbackHandler(LogFallbackHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.messages = []

    async def send_message(self, **kwargs):
        await super().send_message(**kwargs)
        self.messages.append(kwargs)
        return f'msg-id-{len(self.messages)}'

    async def process_webhook(self, request):
        smtp_content = await request.text()
        await self.process_smtp_message(smtp_content)
