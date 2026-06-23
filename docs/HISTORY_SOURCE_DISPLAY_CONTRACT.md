# History Source Display Contract

## API Contract

`GET /api/conversations` and `GET /api/conversations/{id}` return:

- conversation title;
- immutable source file ID/name;
- source availability;
- persisted message list;
- persisted assistant `ChatResponse` snapshots.

History load must not run SQL, call Ollama, or depend on the currently clicked file in the uploaded-files panel.

## UI Contract

The sidebar displays:

- main line: conversation title;
- secondary line: source filename with ellipsis and hover title.

The open chat displays:

- `Using: <source filename>` when available;
- `Source unavailable: <source filename>` when the uploaded file was removed.

Every assistant response renders from its stored `response` payload through the same `ChatMessage` renderer used for live responses.
