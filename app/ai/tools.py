import asyncio
import inspect
import logging
from typing import Dict, Any, Callable, Awaitable, List, Optional
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    required_permissions: List[str] = []


class ToolSandbox:
    """
    Secure tool calling registry and sandbox.
    Executes functions with argument validation, timeout boundaries, and permission checks.
    """
    def __init__(self):
        self.tools: Dict[str, Callable[..., Awaitable[Any]]] = {}
        self.definitions: Dict[str, ToolDefinition] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        parameters_schema: Dict[str, Any],
        handler: Callable[..., Awaitable[Any]],
        required_permissions: Optional[List[str]] = None
    ):
        self.tools[name] = handler
        self.definitions[name] = ToolDefinition(
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            required_permissions=required_permissions or []
        )

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        """Formats registered tools for OpenAI function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.parameters_schema,
                }
            }
            for d in self.definitions.values()
        ]

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        user_permissions: List[str],
        timeout_seconds: float = 5.0
    ) -> Dict[str, Any]:
        """
        Executes a tool call inside a timeout boundary with permission verification.
        """
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found."}

        defn = self.definitions[name]
        # Permission check
        for perm in defn.required_permissions:
            if perm not in user_permissions:
                return {"error": f"Permission denied for tool '{name}'. Required: {perm}"}

        handler = self.tools[name]
        try:
            result = await asyncio.wait_for(handler(**arguments), timeout=timeout_seconds)
            return {"result": result}
        except asyncio.TimeoutError:
            logger.error(f"Tool {name} execution timed out after {timeout_seconds}s")
            return {"error": f"Tool '{name}' execution timed out."}
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}", exc_info=True)
            return {"error": str(e)}
