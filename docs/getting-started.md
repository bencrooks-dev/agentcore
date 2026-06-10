# Getting started

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -U pip
pip install marrow-rt                  # from PyPI (when published)
# or, from source:
pip install git+https://github.com/bencrooks-dev/marrow
```

With real LLM providers:

```bash
pip install 'marrow-rt[openai]'
pip install 'marrow-rt[anthropic]'
pip install 'marrow-rt[ollama]'
pip install 'marrow-rt[all]'
```

## Hello world

```python
from marrow import Agent, Runtime, MockProvider

rt = Runtime()
provider = MockProvider()

agent = rt.add(Agent("assistant", provider, system_prompt="Be concise."))
agent.append_user("What is a graph database?")
print(agent.step())
```

## Use a real provider

```python
from marrow import Agent, Runtime
from marrow.providers import AnthropicProvider

rt = Runtime()
provider = AnthropicProvider(model="claude-sonnet-4-6")
agent = rt.add(Agent("assistant", provider))
agent.append_user("Explain graph databases in one paragraph.")
print(agent.step())
```

## Stream the response

```python
agent.append_user("Now write a haiku about them.")
agent.stream(on_chunk=lambda c: print(c, end="", flush=True))
```

## Add a tool

```python
from marrow import Runtime, ToolBox, tool

@tool(description="Multiply two integers.")
def multiply(a: int, b: int) -> int:
    return a * b

rt = Runtime()
ToolBox().add(multiply).bind(rt)
print(rt.tools.invoke("multiply", '{"a": 6, "b": 7}'))
# {"ok": true, "result": 42}
```

## Govern an existing MCP server (no code)

You don't have to write a graph to use Marrow's governance. Put the
[MCP gateway](concepts/gateway.md) in front of any MCP server your agent
already uses — policy, least privilege, budgets, and a recorded trace, with
zero changes to the agent or server:

```console
$ python examples/gateway/demo.py        # see it deny a destructive tool
$ marrow-trace gateway_trace.json --open # read the flight-recorder report
```

## What to read next

- [Architecture](architecture.md) for the design rationale
- [Compiler](concepts/compiler.md) for graph → ARI → RuntimePlan → trace
- [MCP gateway](concepts/gateway.md) for governing existing agents
- [Flight recorder](concepts/flight-recorder.md) for reading traces
- [Tools](concepts/tools.md) for the full tool-registration story
- [Providers](concepts/providers.md) for plugging in new LLMs
- [Persistence](concepts/persistence.md) for surviving process restarts
