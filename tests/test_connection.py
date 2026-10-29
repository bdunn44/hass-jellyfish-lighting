"""Tests for closing the WebSocket connection to the controller."""

import base64
import hashlib
import socket
import threading

import pytest

from custom_components.jellyfish_lighting.api import JellyfishLightingApiClient

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


@pytest.fixture
def controller_server(socket_enabled):
    """A WebSocket server on the controller's port that never answers a close.

    jellyfishlights-py always connects to port 9000, so the server listens there.
    """
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 9000))
    server.listen()
    server.settimeout(0.1)
    stop = threading.Event()
    threads = []

    def handle(conn):
        conn.settimeout(0.1)
        request = b""
        while b"\r\n\r\n" not in request:
            request += conn.recv(1024)
        key = next(
            line.split(b":", 1)[1].strip()
            for line in request.split(b"\r\n")
            if line.lower().startswith(b"sec-websocket-key")
        )
        accept = base64.b64encode(hashlib.sha1(key + WS_GUID.encode()).digest())
        conn.sendall(
            b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
            b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n"
        )
        while not stop.is_set():
            try:
                if not conn.recv(1024):
                    break
            except TimeoutError:
                continue
        conn.close()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = server.accept()
            except TimeoutError:
                continue
            thread = threading.Thread(target=handle, args=(conn,))
            thread.start()
            threads.append(thread)
        server.close()

    threads.append(threading.Thread(target=serve))
    threads[0].start()
    yield
    stop.set()
    for thread in threads:
        thread.join()


@pytest.fixture
def local_client(hass, config_entry, controller_server):
    return JellyfishLightingApiClient("127.0.0.1", config_entry, hass)


def reader(api):
    """The library's WebSocket reader thread and the raw socket it reads"""
    controller = api._controller
    return (
        controller._JellyFishController__ws_thread,
        controller._JellyFishController__ws.sock.sock,
    )


async def test_disconnect_stops_reader_thread(hass, local_client):
    await local_client.async_connect()
    thread, sock = reader(local_client)

    await local_client.async_disconnect()

    assert not thread.is_alive()
    assert sock.fileno() == -1


async def test_reconnect_stops_old_reader_thread(hass, local_client):
    """The old reader thread must exit before the new connection is made.

    It waits in select() for up to 10s, and if it exits late its on_close marks
    the new connection (which shares the monitor) as disconnected, triggering
    another reconnect.
    """
    await local_client.async_connect()
    thread, sock = reader(local_client)

    # As _note_missed_poll does before reconnecting
    local_client._reconnecting = True
    await local_client._async_reconnect()

    assert not thread.is_alive()
    assert sock.fileno() == -1
    assert local_client.connected
    await local_client.async_disconnect()
