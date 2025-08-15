import asyncio


def pytest_pyfunc_call(pyfuncitem):
    if pyfuncitem.get_closest_marker("asyncio"):
        loop = asyncio.new_event_loop()
        try:
            testargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames}
            loop.run_until_complete(pyfuncitem.obj(**testargs))
        finally:
            loop.close()
        return True


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark async tests")
