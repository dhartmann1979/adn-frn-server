from frnadn.frn.logwatch import LogWatch


def test_systemmanager_error_does_not_mark_listening_java_server_as_stopped():
    watch = LogWatch.__new__(LogWatch)
    watch.service = "active"
    watch.listen = ["10024"]
    watch.started = 123.0
    watch.error = "SystemManager: connection timed out"
    watch.version = "4.15.0 (1234)"
    watch.restarts = 0
    watch.rooms = {}

    state = watch.state()

    assert state["running"] is True
    assert state["service"] == "active"
    assert state["listen"] == ["10024"]
    assert state["warning"] == state["error"]


def test_java_server_without_listening_socket_is_not_reported_as_running():
    watch = LogWatch.__new__(LogWatch)
    watch.service = "active"
    watch.listen = []
    watch.started = None
    watch.error = ""
    watch.version = ""
    watch.restarts = 0
    watch.rooms = {}

    assert watch.state()["running"] is False
