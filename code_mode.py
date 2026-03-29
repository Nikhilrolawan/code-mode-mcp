import subprocess
import textwrap
import json
import sys
import os
import threading
from typing import Annotated
from pydantic import Field
from fastmcp import FastMCP

JSON_TO_PYTHON = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "list",
    "object": "dict",
    "null": "None",
}


def generate_type_stubs(mcp: FastMCP) -> str:
    """Generate Python type stubs from registered MCP tool schemas."""
    lines = ["# Auto-generated type stubs — equivalent to Cloudflare's generateTypes()", "#"]

    for tool_name, tool in mcp._tool_manager._tools.items():
        if tool_name == "execute_code":
            continue

        params = tool.parameters.get("properties", {})
        required = tool.parameters.get("required", [])
        args = []

        for param_name, schema in params.items():
            raw_type = schema.get("type", "any")
            if isinstance(raw_type, list):
                types = [JSON_TO_PYTHON.get(t, "any") for t in raw_type if t != "null"]
                py_type = " | ".join(types) + " | None"
            else:
                py_type = JSON_TO_PYTHON.get(raw_type, "any")
                if param_name not in required:
                    py_type = f"{py_type} | None"

            default = schema.get("default")
            if default is not None:
                args.append(f"{param_name}: {py_type} = {repr(default)}")
            else:
                args.append(f"{param_name}: {py_type} = None")

        sig = ", ".join(args)
        lines.append(f"# {tool_name}({sig}) -> list[dict]")
        lines.append(f"#   {tool.description or ''}")
        lines.append("#")

    return "\n".join(lines)


def generate_proxy_bootstrap(mcp: FastMCP) -> str:
    """
    Generate proxy stubs — equivalent to Cloudflare's Proxy + ToolDispatcher.
    Each function sends a JSON-RPC request to the parent process via stdout
    and waits for the result via stdin, instead of calling the API directly.
    """
    lines = [
        "import json, sys",
        "",
        "def _call_host(tool_name, kwargs):",
        "    request = json.dumps({'tool': tool_name, 'kwargs': kwargs})",
        "    sys.stdout.write(request + '\\n')",
        "    sys.stdout.flush()",
        "    response = sys.stdin.readline()",
        "    data = json.loads(response)",
        "    if 'error' in data:",
        "        raise RuntimeError(data['error'])",
        "    return data['result']",
        "",
    ]

    for tool_name, tool in mcp._tool_manager._tools.items():
        if tool_name == "execute_code":
            continue

        params = tool.parameters.get("properties", {})
        args = []
        call_kwargs = []

        for param_name, schema in params.items():
            default = schema.get("default")
            args.append(f"{param_name}={repr(default)}" if default is not None else f"{param_name}=None")
            call_kwargs.append(f"'{param_name}': {param_name}")

        func_args = ", ".join(args)
        kwargs_dict = "{" + ", ".join(call_kwargs) + "}"

        lines.append(f"def {tool_name}({func_args}):")
        lines.append(f"    return _call_host('{tool_name}', {kwargs_dict})")
        lines.append("")

    return "\n".join(lines)


def build_dispatcher(mcp: FastMCP) -> dict:
    """
    Build a dispatcher mapping tool names to their real implementations.
    Equivalent to Cloudflare's ToolDispatcher extends RpcTarget.
    """
    import httpx

    FAKER_BASE = "https://fakerapi.it/api/v2"

    def make_fetcher(resource: str):
        def fetch(**kwargs):
            params = {}
            for k, v in kwargs.items():
                if v is None:
                    continue
                if k in ("quantity", "locale", "seed"):
                    params[f"_{k}"] = v
                else:
                    params[k] = v
            r = httpx.get(f"{FAKER_BASE}/{resource}", params=params, timeout=10)
            r.raise_for_status()
            return r.json()["data"]
        return fetch

    dispatcher = {}
    for tool_name in mcp._tool_manager._tools:
        if tool_name == "execute_code":
            continue
        resource = tool_name.replace("get_", "")
        dispatcher[tool_name] = make_fetcher(resource)

    return dispatcher


def run_dispatcher_loop(proc, dispatcher: dict):
    """
    Read JSON-RPC requests from subprocess stdout and dispatch to real tool functions.
    Equivalent to Cloudflare's Workers RPC host-side handler.
    Runs in a separate thread so it doesn't block the main process.
    """
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            tool_name = request["tool"]
            kwargs = request["kwargs"]

            if tool_name not in dispatcher:
                response = {"error": f"Unknown tool: {tool_name}"}
            else:
                result = dispatcher[tool_name](**kwargs)
                response = {"result": result}
        except Exception as e:
            response = {"error": str(e)}

        proc.stdin.write(json.dumps(response) + "\n")
        proc.stdin.flush()


def make_execute_code(mcp: FastMCP):
    """
    Returns the execute_code tool function.
    The subprocess runs LLM-written code with proxy stubs.
    The parent dispatches real tool calls back via JSON-RPC over pipes.
    Equivalent to Cloudflare's createCodeTool + DynamicWorkerExecutor pattern.
    """
    dispatcher = build_dispatcher(mcp)

    def execute_code(
        code: Annotated[str, Field(description=(
            "Python code to execute. Must define def run(): or async def run(): and return the result. "
            "Call tool functions directly e.g. get_books(quantity=3). "
            "Do not import anything — all functions are pre-injected."
        ))]
    ) -> dict:
        stubs = generate_type_stubs(mcp)
        proxy = generate_proxy_bootstrap(mcp)

        wrapper = textwrap.dedent(f"""
{stubs}

{proxy}

import asyncio

{code}

result = asyncio.run(run()) if asyncio.iscoroutinefunction(run) else run()

import sys, json
sys.stdout.write(json.dumps({{"final": result}}) + "\\n")
sys.stdout.flush()
""")

        proc = subprocess.Popen(
            [sys.executable, "-c", wrapper],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )

        # run dispatcher in a thread — handles all RPC calls from subprocess
        # equivalent to Workers RPC host-side handler
        final_result = {}
        dispatcher_done = threading.Event()

        def dispatch_loop():
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)

                    # final result marker — subprocess is done
                    if "final" in data:
                        final_result["result"] = data["final"]
                        break

                    # RPC call from subprocess proxy
                    tool_name = data["tool"]
                    kwargs = data["kwargs"]

                    if tool_name not in dispatcher:
                        response = {"error": f"Unknown tool: {tool_name}"}
                    else:
                        result = dispatcher[tool_name](**kwargs)
                        response = {"result": result}

                except Exception as e:
                    response = {"error": str(e)}

                proc.stdin.write(json.dumps(response) + "\n")
                proc.stdin.flush()

            dispatcher_done.set()

        thread = threading.Thread(target=dispatch_loop, daemon=True)
        thread.start()

        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            return {"error": "execution timed out"}

        dispatcher_done.wait(timeout=5)

        if proc.returncode != 0:
            return {"error": proc.stderr.read().strip()}

        return final_result if final_result else {"error": "no result returned"}

    return execute_code