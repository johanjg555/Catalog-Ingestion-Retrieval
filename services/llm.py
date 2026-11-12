import asyncio
import json
import redis.asyncio as redis

from core.config import settings
from core.logging import get_logger
from utils.search_product import get_current_date, get_eol_info
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url=settings.llama_server_url,
    api_key="ollama",
)

logger = get_logger(__name__)

my_tools_list = [
    {
        "type": "function",
        "function": {
            "name": "get_current_date",
            "description": "Get the current date",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_eol_info",
            "description": "Check the End of Life (EOL) or obsolete status of the requested product.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "The exact name or model of the product to check."
                    }
                },
                "required": ["product_name"]
            }
        }
    }
]

def build_tool_query(query: str, retrieved_context: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are an assistant determining product lifecycle status. "
                "If the user asks about replacing or checking an old product, use a tool if necessary"
            )
        },
        {
            "role": "user",
            "content": f"Context:\n{retrieved_context}\n\nQuestion:\n{query}"
        }
    ]

def build_final_messages(query: str, retrieved_context: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a technical assistant. Review the user request and any tool "
                "outputs provided below. Only suggest replacements that are NOT end-of-life. "
                "Be highly concise."
            )
        },
        {
            "role": "user",
            "content": f"Context:\n{retrieved_context}\n\nQuestion:\n{query}"
        }
    ]

async def redis_publisher(task_id: str, pub_queue: asyncio.Queue[str | None]) -> None:
    r = redis.from_url(settings.redis_url)
    channel = f"stream:{task_id}"

    try:
        while True:
            token = await pub_queue.get()
            if token is None:
                break
            await r.publish(channel, token)
    finally:
        await r.publish(channel, "[DONE]")
        await r.aclose()


async def stream_rag_response(query: str, retrieved_context: str, reranked_docs: list[str], task_id=None):
     
    async def wrapped_get_eol_info(product_name=None):
        return await get_eol_info(reranked_docs)

    available_functions = {
        "get_current_date": get_current_date,
        "get_eol_info": wrapped_get_eol_info
    }

    messages = build_final_messages(query, retrieved_context)
    tool_query = build_tool_query(query, retrieved_context)

    pub_queue: asyncio.Queue[str | None] | None = asyncio.Queue(maxsize=100) if task_id else None
    publisher_task = asyncio.create_task(redis_publisher(task_id, pub_queue)) if pub_queue else None

    try: 
        response = await client.chat.completions.create(
            model="llama-3.2",
            messages=tool_query,
            max_tokens=256,
            temperature=0.0,
            tools=my_tools_list,
            tool_choice="auto",
            parallel_tool_calls=True,
            
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        print("response:", response_message.content)
        print("tool_calls:", tool_calls)

        if tool_calls:
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_to_call = available_functions.get(function_name)
                
                if function_to_call:
                    try:
                        function_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        function_args = {}
                    
                    if asyncio.iscoroutinefunction(function_to_call):
                        function_response = await function_to_call(**function_args)
                    else:
                        function_response = function_to_call(**function_args)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": function_response,
                    })

        stream = await client.chat.completions.create(
            model="llama-3.2",
            messages=messages,
            max_tokens=256,
            temperature=0.2,
            stream=True,
        )

        async for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                if pub_queue: await pub_queue.put(token)
                yield token

    finally:
        if pub_queue:
            await pub_queue.put(None)
            if publisher_task:
                await publisher_task