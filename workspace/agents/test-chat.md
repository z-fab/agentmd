---
name: test-chat
description: Tests chat mode — conversation memory via checkpointer
model:
  provider: google
  name: gemini-2.5-flash
settings:
  max_tool_calls: 5
  timeout: 30
history: low
---
You are a friendly assistant for testing chat. Keep responses very short (1-2 sentences).
When the user tells you something, remember it and recall it when asked.
