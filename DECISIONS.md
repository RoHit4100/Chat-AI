# Architectural Decisions

## Dual State Stores: Database Display History vs. Agent Checkpoint

### Context
The system maintains conversation state across two persistence layers:
1. **Relational Database (`Message` rows)**:
   - Serves as the authoritative record for user display history in the UI.
   - Stores user messages, assistant responses, final statuses (`complete`, `failed`, `stopped`), token usage counts, and associated file metadata.
2. **LangGraph Checkpointer (`AsyncPostgresSaver`)**:
   - Serves as the agent's working state machine memory across turns and restarts.
   - Contains intermediate execution state: system prompts, tool call objects, tool execution results, rolling summaries, manifests, and consecutive error counters.

---

### Which Store Wins

#### 1. Display History Precedence
The database `Message` table is the user-facing source of truth. The LangGraph checkpoint is an execution cache and state machine checkpoint.

#### 2. Handling Regeneration (`POST /api/threads/<id>/regenerate`)
- When a user triggers regeneration, the display history wins.
- The assistant's prior turn (including any intermediate tool calls and tool responses) is removed from the checkpoint using LangGraph's `RemoveMessage`.
- The agent re-runs beginning from the last valid user message.
- The existing assistant `Message` record in the database is replaced with the newly generated response.

#### 3. Handling Stream Failures and Client Aborts
- If a client disconnects or aborts a stream, execution halts and the collected content is saved to the database with `status="stopped"`.
- If an unrecoverable exception occurs, the assistant message is saved with `status="failed"`.
- If a mismatch ever occurs between the database display history and checkpoint state (such as an unhandled container crash mid-turn), the checkpoint is reconciled and trimmed using `RemoveMessage` to match the persisted `Message` rows before resuming execution.
