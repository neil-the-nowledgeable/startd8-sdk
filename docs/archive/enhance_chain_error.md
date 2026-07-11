════════════════════════════════════════════════════════════════════════════════
                    startd8 - Multi-LLM Benchmarking System
                          Executing Enhancement Chain
════════════════════════════════════════════════════════════════════════════════


Step 1/3: anthropic:claude-3-opus-20240229
Enhancing document...
✓ Complete (141200ms, 11,302 tokens, $0.4153)

Step 2/3: openai:gpt-4
Enhancing document...
✓ Complete (128588ms, 7,406 tokens, $0.3276)

Step 3/3: cursorAI_Composor
Enhancing document...
API call failed for cursorAI_Composor: Connection error.
Traceback (most recent call last):
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpx/_transports/default.py", line 101, in
map_httpcore_exceptions
    yield
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpx/_transports/default.py", line 394, in
handle_async_request
    resp = await self._pool.handle_async_request(req)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpcore/_async/connection_pool.py", line 256, in
handle_async_request
    raise exc from None
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpcore/_async/connection_pool.py", line 236, in
handle_async_request
    response = await connection.handle_async_request(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        pool_request.request
        ^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpcore/_async/connection.py", line 101, in
handle_async_request
    raise exc
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpcore/_async/connection.py", line 78, in
handle_async_request
    stream = await self._connect(request)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpcore/_async/connection.py", line 124, in _connect
    stream = await self._network_backend.connect_tcp(**kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpcore/_backends/auto.py", line 31, in connect_tcp
    return await self._backend.connect_tcp(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<5 lines>...
    )
    ^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpcore/_backends/anyio.py", line 113, in connect_tcp
    with map_exceptions(exc_map):
         ~~~~~~~~~~~~~~^^^^^^^^^
  File "/opt/homebrew/Cellar/python@3.14/3.14.2/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 162, in __exit__
    self.gen.throw(value)
    ~~~~~~~~~~~~~~^^^^^^^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpcore/_exceptions.py", line 14, in map_exceptions
    raise to_exc(exc) from exc
httpcore.ConnectError: [Errno 8] nodename nor servname provided, or not known

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/openai/_base_client.py", line 1529, in request
    response = await self._client.send(
               ^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
    )
    ^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpx/_client.py", line 1629, in send
    response = await self._send_handling_auth(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<4 lines>...
    )
    ^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpx/_client.py", line 1657, in _send_handling_auth
    response = await self._send_handling_redirects(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
    )
    ^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpx/_client.py", line 1694, in _send_handling_redirects
    response = await self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpx/_client.py", line 1730, in _send_single_request
    response = await transport.handle_async_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpx/_transports/default.py", line 393, in
handle_async_request
    with map_httpcore_exceptions():
         ~~~~~~~~~~~~~~~~~~~~~~~^^
  File "/opt/homebrew/Cellar/python@3.14/3.14.2/Frameworks/Python.framework/Versions/3.14/lib/python3.14/contextlib.py", line 162, in __exit__
    self.gen.throw(value)
    ~~~~~~~~~~~~~~^^^^^^^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/httpx/_transports/default.py", line 118, in
map_httpcore_exceptions
    raise mapped_exc(message) from exc
httpx.ConnectError: [Errno 8] nodename nor servname provided, or not known

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/Users/neilyashinsky/Documents/Startd8/dev/startd8-sdk-project/src/startd8/agents.py", line 718, in agenerate
    response = await self.async_client.chat.completions.create(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<5 lines>...
    )
    ^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/openai/resources/chat/completions/completions.py", line
2678, in create
    return await self._post(
           ^^^^^^^^^^^^^^^^^
    ...<49 lines>...
    )
    ^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/openai/_base_client.py", line 1794, in post
    return await self.request(cast_to, opts, stream=stream, stream_cls=stream_cls)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/neilyashinsky/.local/pipx/venvs/startd8/lib/python3.14/site-packages/openai/_base_client.py", line 1561, in request
    raise APIConnectionError(request=request) from err
openai.APIConnectionError: Connection error.
✗ Failed: API call failed: Connection error.
  Running enhancement chain...