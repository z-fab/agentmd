# Custom Tools

Extend Agent.md with custom Python tools that add domain-specific capabilities beyond the built-in tools. Custom tools are Python files with `@tool`-decorated functions that agents can call during execution.

## Quick Start

### 1. Create a Tool File

Create a Python file in `workspace/agents/tools/`:

```python
# workspace/agents/tools/sentiment_analyzer.py
from langchain_core.tools import tool

@tool
def analyze_sentiment(text: str) -> str:
    """Analyze the sentiment of the given text.

    Args:
        text: The text to analyze.

    Returns:
        Sentiment classification: positive, negative, or neutral.
    """
    positive_words = ["good", "great", "excellent", "happy", "love"]
    negative_words = ["bad", "terrible", "awful", "hate", "sad"]

    text_lower = text.lower()
    pos_count = sum(word in text_lower for word in positive_words)
    neg_count = sum(word in text_lower for word in negative_words)

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    else:
        return "neutral"
```

### 2. Declare the Tool in Agent Frontmatter

Reference the tool file (without `.py` extension) in the `custom_tools` field:

```yaml
---
name: review-analyzer
custom_tools:
  - sentiment_analyzer
---

You are a product review analyzer.
Read reviews from `reviews.txt` and use the `analyze_sentiment` tool to classify each review.
Write a summary to `sentiment-report.txt`.
```

### 3. Run the Agent

```bash
agentmd run review-analyzer
```

The agent now has access to `analyze_sentiment` alongside the built-in tools.

---

## The @tool Decorator

The `@tool` decorator from LangChain converts a regular Python function into a tool that LLMs can call.

### Requirements

1. **Docstring is required**: The first line becomes the tool description shown to the LLM
2. **Type hints are required**: Parameters must have type annotations (`str`, `int`, `float`, `bool`, `dict`, `list`)
3. **Return type**: Must return a string (or be converted to string)
4. **Args documentation**: Use Google-style docstrings to document parameters

```python
from langchain_core.tools import tool

@tool
def my_tool(param: str, count: int) -> str:
    """Tool description that the LLM sees.

    Args:
        param: Parameter description.
        count: Numeric parameter.

    Returns:
        What the tool returns.
    """
    return f"Processed: {param} x {count}"
```

### Supported Parameter Types

```python
@tool
def example_tool(
    text: str,
    count: int,
    threshold: float,
    enabled: bool,
    options: dict,
    items: list,
) -> str:
    """Example showing all supported parameter types."""
    return f"Received: {text}, {count}, {threshold}"
```

---

## File Location & Naming

All custom tools must be in:

```
workspace/agents/tools/
```

Each Python file can contain one or more `@tool`-decorated functions.

### Naming Conventions

- **File names**: `snake_case.py` (e.g., `sentiment_analyzer.py`)
- **Function names**: `snake_case` (e.g., `analyze_sentiment`)
- **Tool names in frontmatter**: Match the file name without `.py`

### Single-Tool Files

Most common pattern: one tool per file.

```python
# workspace/agents/tools/word_counter.py
from langchain_core.tools import tool

@tool
def count_words(text: str) -> str:
    """Count the number of words in the given text.

    Args:
        text: The text to analyze.

    Returns:
        Word count as a string.
    """
    return f"Word count: {len(text.split())}"
```

Declare in frontmatter: `custom_tools: [word_counter]`

### Multi-Tool Files

One file can export multiple related tools. All `@tool`-decorated functions are loaded automatically:

```python
# workspace/agents/tools/text_utils.py
from langchain_core.tools import tool

@tool
def count_words(text: str) -> str:
    """Count words in text."""
    return str(len(text.split()))

@tool
def to_uppercase(text: str) -> str:
    """Convert text to uppercase."""
    return text.upper()
```

Declare in frontmatter: `custom_tools: [text_utils]`

---

## Examples

### Example 1: API Integration

```python
# workspace/agents/tools/weather_api.py
from langchain_core.tools import tool
import httpx
import os

@tool
def get_weather(city: str) -> str:
    """Fetch current weather for a city using OpenWeatherMap API.

    Args:
        city: City name (e.g., "London", "New York").

    Returns:
        Weather description and temperature.
    """
    api_key = os.environ.get("OPENWEATHER_API_KEY")
    if not api_key:
        return "ERROR: OPENWEATHER_API_KEY not set"

    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"

    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        temp = data["main"]["temp"]
        description = data["weather"][0]["description"]
        return f"{city}: {description}, {temp}°C"
    except Exception as e:
        return f"ERROR: {e}"
```

Usage in agent:
```yaml
custom_tools: [weather_api]
```

### Example 2: Data Processing

```python
# workspace/agents/tools/csv_parser.py
from langchain_core.tools import tool
import csv
from io import StringIO

@tool
def parse_csv(csv_content: str) -> str:
    """Parse CSV content and return row count and column names.

    Args:
        csv_content: CSV data as a string.

    Returns:
        Summary of the CSV structure.
    """
    try:
        reader = csv.DictReader(StringIO(csv_content))
        rows = list(reader)

        if not rows:
            return "Empty CSV"

        columns = list(rows[0].keys())
        return f"Columns: {', '.join(columns)}\nRows: {len(rows)}"
    except Exception as e:
        return f"ERROR parsing CSV: {e}"
```

Usage in agent:
```yaml
custom_tools: [csv_parser]
paths:
  - data/
```

### Example 3: Text Transformation

```python
# workspace/agents/tools/markdown_converter.py
from langchain_core.tools import tool

@tool
def markdown_to_html(markdown: str) -> str:
    """Convert Markdown to HTML.

    Args:
        markdown: Markdown-formatted text.

    Returns:
        HTML string.
    """
    try:
        import markdown
        return markdown.markdown(markdown)
    except ImportError:
        return "ERROR: markdown package not installed. Run: pip install markdown"
    except Exception as e:
        return f"ERROR: {e}"
```

Usage in agent:
```yaml
custom_tools: [markdown_converter]
paths:
  - content/
  - html/
```

---

## Dependencies

Custom tools can use any Python package available in your environment.

### Installing Packages

```bash
uv pip install markdown
uv pip install pandas
uv pip install httpx
```

### Handling Missing Dependencies

Always check for import errors and return helpful messages:

```python
@tool
def advanced_analysis(data: str) -> str:
    """Analyze data using pandas."""
    try:
        import pandas as pd
    except ImportError:
        return "ERROR: pandas not installed. Run: pip install pandas"

    # Tool logic here
    return "Analysis complete"
```

---

## Declaring Tools in Frontmatter

Use the `custom_tools` field (or `tools` alias) to declare which tools the agent can access.

```yaml
custom_tools:
  - sentiment_analyzer
  - weather_api
  - csv_parser
```

Built-in tools (`file_read`, `file_write`, `file_list`, `http_request`) are always available. Custom tools are added on top.

---

## Troubleshooting

### Tool file not found

**Error:**
```
FileNotFoundError: Custom tool 'my_tool' not found: expected file at workspace/agents/tools/my_tool.py
```

**Solution:**
1. Check that the file exists at `workspace/agents/tools/my_tool.py`
2. Verify the file name matches the `custom_tools` declaration
3. File names are case-sensitive on Linux/macOS

### No @tool definitions found

**Error:**
```
ValueError: Custom tool file 'my_tool.py' contains no @tool definitions.
```

**Solution:**
```python
from langchain_core.tools import tool

@tool
def my_function(input: str) -> str:
    """Description."""
    return input
```

Import from `langchain_core.tools`, not `langchain.tools`.

### Missing docstring or type hints

**Error:**
```
ValueError: Tool function must have a docstring
ValidationError: Field 'param' requires type annotation
```

**Solution:**
```python
@tool
def my_tool(param: str, count: int) -> str:
    """This is the tool description.

    Args:
        param: Parameter description.
        count: Parameter description.

    Returns:
        What the tool returns.
    """
    return f"{param} x {count}"
```

### Tool not loaded

**Problem:** Agent says "I don't have access to that tool"

**Solution:**
1. Check that the tool is declared in `custom_tools`
2. Verify the tool file is in `workspace/agents/tools/`
3. Check logs: `agentmd run agent -vv`

### Import errors in tool

**Problem:** Tool returns "ERROR: module 'X' not found"

**Solution:**
```bash
uv pip install X
```

And add error handling in the tool.

---

## Best Practices

### 1. Keep Tools Focused

Each tool should do one thing well:

```python
# Good: separate focused tools
@tool
def to_uppercase(text: str) -> str:
    """Convert text to uppercase."""
    return text.upper()

@tool
def count_chars(text: str) -> str:
    """Count characters in text."""
    return str(len(text))
```

### 2. Return Strings

Tools should always return strings. For structured data, use JSON:

```python
import json

@tool
def get_user_info(user_id: int) -> str:
    """Get user information."""
    user = {"id": user_id, "name": "Alice", "email": "alice@example.com"}
    return json.dumps(user, indent=2)
```

### 3. Handle Errors Gracefully

Always catch exceptions and return error messages:

```python
@tool
def risky_operation(input: str) -> str:
    """Perform a risky operation."""
    try:
        result = do_something(input)
        return f"Success: {result}"
    except Exception as e:
        return f"ERROR: {e}"
```

### 4. Use Environment Variables for Secrets

Never hardcode API keys:

```python
import os

@tool
def call_api(endpoint: str) -> str:
    """Call external API."""
    api_key = os.environ.get("API_KEY")
    if not api_key:
        return "ERROR: API_KEY environment variable not set"
    # Use api_key in request
    return "API response"
```

### 5. Document Clearly

Write clear docstrings that help the LLM understand when to use the tool:

```python
@tool
def analyze_sentiment(text: str) -> str:
    """Analyze the sentiment of text (positive, negative, or neutral).

    Use this tool to classify the emotional tone of reviews, comments, or feedback.

    Args:
        text: The text to analyze (sentences or paragraphs).

    Returns:
        Sentiment classification: "positive", "negative", or "neutral".
    """
    # Implementation
```

### 6. Reuse Tools Across Agents

Create generic, reusable tools:

```
workspace/agents/tools/
├── text_utils.py       # Used by many agents
├── weather_api.py      # Weather agents
├── csv_parser.py       # Data processing agents
└── markdown_converter.py
```

---

## Next Steps

- [Built-in tools reference →](built-in-tools.md)
- [MCP integration →](mcp-integration.md)
- [Agent examples →](../examples.md)
