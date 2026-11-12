
from ddgs import DDGS
from datetime import datetime, timezone
from core.logging import get_logger

logger = get_logger(__name__)

_ddgs = None
def get_ddgs():
    global _ddgs
    if _ddgs is None:
        _ddgs = DDGS(api_url="http://localhost:4479", spawn_api=True)
        logger.info("ddgs_initialized")
    return _ddgs




async def get_component_status(part_number: str) -> str:
    """Search for the lifecycle status of a specific part."""
    query = f"{part_number} End-of-Life (EOL) status"

    ddgs = get_ddgs()
    try:
        results = ddgs.text(query, max_results=2)
    except:
        return "Not Found"

    content=[]
    for r in results:
        print(f"Title: {r['title']}")
        print(f"Snippet: {r['body']}")
        print(f"URL: {r['href']}\n")


        content.append(r['body'])

    return "\n".join(content)
        
        
async def get_eol_info(reranked_docs: list[str]):
    product_ids=set()
    eol_info=[]
    for content in reranked_docs:
        sku_line = next(
            (line for line in content.splitlines() if line.startswith("SKU:")),
            None,
        )
        if sku_line is None:
            continue
        sku = sku_line.partition(":")[2].strip()
        if not sku:
            continue

        if sku in product_ids:
            continue
        else:
            status_raw=await get_component_status(sku)
            eol_info.append("SKU:"+sku+"\tStatus:"+str(status_raw))
            product_ids.add(sku)
            
    return "\n".join(eol_info)

async def get_current_date():
    return datetime.now(timezone.utc).date()






  