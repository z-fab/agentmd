---
name: hello
description: Generate a creative greeting message. Use when the agent needs to create personalized greetings.
argument-hint: "[name]"
---

# Creative Greeting Generator

Generate a creative and unique greeting for **$ARGUMENTS**.

## Steps

1. First, read the greeting styles reference with: `skill_read_file("hello", "references/greeting-styles.md")`
2. Optionally, get a fun fact with: `skill_run_script("hello", "random_fact.py")`
3. Generate a creative and original greeting using the styles as inspiration
4. Include the fun fact
5. Keep it under 3 sentences

## Context

System info: !`uname -s`
