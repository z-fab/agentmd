---
name: test-basic
description: Basic run test — verifies backend + SSE + tools
model:
  provider: google
  name: gemini-2.5-flash
settings:
  max_tool_calls: 5
  timeout: 30
history: off
paths:
  work_dir: workspace/output
---
You are a test agent. When asked to execute your task:

1. Use file_write to create a file at {work_dir}/basic-test.txt with content "v0.9 basic test passed"
2. Use file_read to read the file you just created
3. Report back with the file content
