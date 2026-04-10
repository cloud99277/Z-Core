Review the conversation transcript and extract durable memories worth saving for future sessions.

Classification guide:
1. `preference`: user preferences, working style, coding conventions, tool habits
2. `fact`: stable project or environment facts, constraints, architecture details
3. `learning`: non-obvious lessons, pitfalls, debugging discoveries, usage patterns
4. `decision`: explicit choices between alternatives, ideally with a reason

Rules:
- Extract only information likely to matter in future conversations.
- Do not capture transient status updates, one-off TODOs, or noisy debugging logs.
- Each entry must be a single self-contained statement under 200 characters.
- Prefer concrete wording over vague summaries.
- Avoid duplicating memories that already exist.
- Return valid JSON only, with no prose before or after it.

Output format:
[
  {{
    "type": "preference|fact|learning|decision",
    "content": "single durable memory",
    "topic": "topic-name",
    "confidence": 0.0
  }}
]

Existing memories:
{existing_memories}

Conversation transcript:
{conversation}
