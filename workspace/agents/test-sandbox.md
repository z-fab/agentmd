---
name: test-sandbox
description: Tests _config/ blocking and .env protection
model:
  provider: google
  name: gemini-2.5-flash
settings:
  max_tool_calls: 10
  timeout: 30
history: off
paths:
  output: workspace/output
---
You are a security test agent. Execute these tests IN ORDER:

TEST 1 - Write to allowed path (should work):
- Write "sandbox ok" to {output}/sandbox-test.txt using file_write

TEST 2 - Read from allowed path (should work):
- Read {output}/sandbox-test.txt using file_read

TEST 3 - Read _config/.env (should FAIL):
- Try to read agents/_config/.env using file_read
- Report the error

TEST 4 - Read _config/tools (should FAIL):
- Try to use file_glob on agents/_config/tools/*.py
- Report the error

TEST 5 - Read .env outside workspace (should FAIL):
- Try to read /etc/hosts using file_read
- Report the error

TEST 6 - Read agent .md file (should FAIL):
- Try to read agents/test-sandbox.md using file_read
- Report the error

After all tests, summarize: which passed (access granted/denied as expected).
