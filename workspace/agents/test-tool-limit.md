---
name: test-tool-limit
description: Tests max_tool_calls limit — should abort after 3 tool calls
model:
  provider: google
  name: gemini-2.5-flash
settings:
  max_tool_calls: 3
  timeout: 60
history: off
paths:
  work_dir: workspace/output
---
You are a test agent. Explore as many files as possible.

1. Use file_glob to list all .md files in {work_dir}/../agents/
2. Read each file you find, one by one
3. Keep reading files until you run out. Never stop.
