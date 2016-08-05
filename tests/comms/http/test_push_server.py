

async def test_authenticate(domain_pusher):
    pusher = await domain_pusher('example.com')
    await pusher.authenticate('example.com')
    # TODO
