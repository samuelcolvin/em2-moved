from em2.fallback import LogFallbackHandler


class TestFallbackHandler(LogFallbackHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.messages = []

    async def send_message(self, **kwargs):
        await super().send_message(**kwargs)
        self.messages.append(kwargs)
