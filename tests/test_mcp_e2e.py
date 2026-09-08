"""End-to-end over the real MCP stdio transport.

dispatch() being tested is not the same as the SERVER working: initialization,
tool listing, argument marshalling and error shape all live in the transport.
"""
import json
import os
import sys
import pytest

from optional import require_module

require_module("mcp", "the stdio transport is what these tests exercise")
anyio = require_module("anyio", "the stdio transport needs an async runtime")

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SRC = os.path.join(os.path.dirname(__file__), "..", "src")


def _params(home, workspace="mcpws"):
    env = dict(os.environ)
    env.update({"BLACKBOARD_HOME": str(home), "PYTHONPATH": os.path.abspath(SRC)})
    return StdioServerParameters(
        command=sys.executable,
        args=["-c", f"from blackboard.server import serve_stdio; "
                    f"raise SystemExit(serve_stdio({workspace!r}))"],
        env=env,
    )


def _run(coro):
    return anyio.run(coro)


def test_server_lists_exactly_the_five_tools(tmp_path):
    async def main():
        async with stdio_client(_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return [t.name for t in (await s.list_tools()).tools]
    assert _run(main) == ["get_state", "update_state", "list_keys",
                          "search_keys", "link_state"]


def test_full_write_read_cycle_over_the_wire(tmp_path):
    U = "bb://mcpws/domain.automotive/fact/brake"

    async def main():
        async with stdio_client(_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                out = []
                res = await s.call_tool("update_state", {
                    "uri": U, "body": {"pads": 4, "rotor_mm": 22},
                    "digest": "brake assembly: 4 pads, 22mm rotor"})
                out.append(json.loads(res.content[0].text))
                res = await s.call_tool("get_state", {"uris": [U]})
                out.append(json.loads(res.content[0].text))
                res = await s.call_tool("get_state", {"uris": [U], "mode": "full"})
                out.append(json.loads(res.content[0].text))
                res = await s.call_tool("list_keys", {"topic": "**", "mode": "table"})
                out.append(json.loads(res.content[0].text))
                res = await s.call_tool("search_keys", {"q": "brake"})
                out.append(json.loads(res.content[0].text))
                return out

    put, dig, full, tbl, srch = _run(main)
    assert put["version"] == 1
    assert dig["items"][0]["digest"] == "brake assembly: 4 pads, 22mm rotor"
    assert "content" not in dig["items"][0], "digest mode must not return a body"
    assert "<bb:body" in full["items"][0]["content"], "bodies must be delimited as untrusted"
    assert tbl["format"] == "tsv" and tbl["rows"] == 1
    assert srch["items"][0]["uri"] == U


def test_errors_cross_the_wire_as_typed_json(tmp_path):
    async def main():
        async with stdio_client(_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool("update_state",
                                        {"uri": "bb://mcpws/t/fact/x", "body": {"a": 1}})
                return json.loads(res.content[0].text)
    err = _run(main)
    assert err["error"] == "DIGEST_REQUIRED"
    assert "digest" in err["message"]


def test_cas_conflict_is_actionable_over_the_wire(tmp_path):
    U = "bb://mcpws/t/fact/cas"

    async def main():
        async with stdio_client(_params(tmp_path)) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                await s.call_tool("update_state", {"uri": U, "body": {"v": 1}, "digest": "d"})
                await s.call_tool("update_state", {"uri": U, "body": {"v": 2}, "digest": "d"})
                res = await s.call_tool("update_state", {
                    "uri": U, "body": {"v": 3}, "digest": "d", "expect_version": 1})
                return json.loads(res.content[0].text)
    err = _run(main)
    assert err["error"] == "VERSION_CONFLICT"
    assert err["current_version"] == 2, "a 409 must tell the caller what to re-read"
