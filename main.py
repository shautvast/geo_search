import anthropic
import requests
import base64
import time
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()

OVERPASS_URL = "http://localhost/api/interpreter"
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

def query_overpass(ql):
    response = requests.post(OVERPASS_URL, data={"data": ql})
    return response.json()

def web_search(query):
    from serpapi import GoogleSearch
    results = GoogleSearch({"q": query, "num": 5, "api_key": SERPAPI_KEY}).get_dict()
    return [{"title": r["title"], "snippet": r.get("snippet", "")} for r in results.get("organic_results", [])]

def encode_image(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def geolocate(image_path):
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": encode_image(image_path)
                    }
                },
                {
                    "type": "text",
                    "text": "Analyze this image for geographic signals and geolocate it."
                }
            ]
        }
    ]

    tools = [
        {
            "name": "overpass_query",
            "description": "Query OpenStreetMap via Overpass QL to find geographic features",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The Overpass QL query"
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Why you're running this query"
                    }
                },
                "required": ["query", "reasoning"]
            }
        },
        {
            "name": "ask_human",
            "description": "Ask the human for additional information or clarification that might help narrow down the location",
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to ask the human"}
                },
                "required": ["question"]
            }
        },
        {
            "name": "google_search",
            "description": "Search the web for named entities like company names, brands, logos, or unique landmarks",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "reasoning": {"type": "string", "description": "Why you're searching this"}
                },
                "required": ["query", "reasoning"]
            }
        },
        {
            "name": "final_answer",
            "description": "Return final location estimate when confident enough",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "reasoning": {"type": "string"},
                    "coordinates": {
                        "type": "object",
                        "properties": {
                            "lat": {"type": "number"},
                            "lon": {"type": "number"}
                        }
                    }
                },
                "required": ["location", "confidence", "reasoning"]
            }
        }
    ]

    system = """You are a geolocation expert. Analyze images for geographic signals and
use Overpass QL queries to narrow down locations.

Strategy:
1. First identify all visual signals (architecture, vegetation, signage, infrastructure, logos, text)
2. Use google_search for named entities: company names, brands, logos, unique landmark names, visible text
3. Use overpass_query for physical/geographic features: road types, building styles, vegetation, infrastructure
4. Use query results to progressively narrow the search area
5. Combine signals from both tools in follow-up queries
5. Use ask_human if you need clarification or additional context the image doesn't provide
6. Call final_answer when confident, or when you've exhausted useful signals

Be precise with OverpassQL. Prefer area-scoped queries once you have a candidate region."""

    # The loop
    while True:
        for attempt in range(5):
            try:
                response = client.messages.create(
                    model="claude-opus-4-5",
                    max_tokens=4096,
                    system=system,
                    tools=tools,
                    messages=messages
                )
                break
            except anthropic.RateLimitError:
                if attempt == 4:
                    raise
                wait = 2 ** attempt * 10
                print(f"Rate limited, retrying in {wait}s...")
                time.sleep(wait)

        # Append assistant response to history
        messages.append({"role": "assistant", "content": response.content})

        # Check stop reason
        if response.stop_reason == "end_turn":
            print("Model stopped without calling a tool")
            break

        # Process tool calls
        tool_results = []
        done = False

        for block in response.content:
            if block.type != "tool_use":
                continue

            if block.name == "ask_human":
                answer = input(f"\n[Human input needed] {block.input['question']}\n> ")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": answer
                })

            elif block.name == "final_answer":
                print(f"Location: {block.input['location']}")
                print(f"Confidence: {block.input['confidence']}")
                print(f"Reasoning: {block.input['reasoning']}")
                done = True
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": "Answer recorded."
                })

            elif block.name == "google_search":
                print(f"\nSearching: {block.input['reasoning']}")
                print(f"Query: {block.input['query']}")
                try:
                    results = web_search(block.input['query'])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(results)
                    })
                    print(f"Got {len(results)} results")
                except Exception as e:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Search failed: {str(e)}",
                        "is_error": True
                    })

            elif block.name == "overpass_query":
                print(f"\nQuerying: {block.input['reasoning']}")
                print(f"QL: {block.input['query']}")
                try:
                    result = query_overpass(block.input['query'])
                    # Truncate if huge
                    elements = result.get("elements", [])[:50]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str({"elements": elements, "count": len(result.get("elements", []))})
                    })
                    print(f"Got {len(result.get('elements', []))} results")
                except Exception as e:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"Query failed: {str(e)}",
                        "is_error": True
                    })

        # Append tool results and continue loop
        messages.append({"role": "user", "content": tool_results})

        if done:
            human_input = input("\nAnything to add? (press Enter to quit) > ").strip()
            if not human_input:
                break
            messages.append({"role": "user", "content": human_input})

if __name__ == "__main__":
    import sys
    geolocate(sys.argv[1])
