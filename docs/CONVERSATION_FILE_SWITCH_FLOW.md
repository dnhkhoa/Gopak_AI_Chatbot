# Conversation File Switch Flow

## Frontend Flow

When the current conversation already has `source_file_id` and the user selects a different Ready file:

1. The current conversation is left unchanged.
2. If the composer has a draft, the user confirms starting a new chat.
3. The frontend calls `POST /api/conversations` with `source_file_id`.
4. The UI navigates to the new conversation.
5. The draft is kept in the composer and is not sent automatically.

If the current conversation has no source yet, selecting a Ready file first-binds that conversation through the compatibility endpoint.

## Sidebar And Header

History items display title as the main line and the source filename as a compact subtitle. The chat header/composer area shows `Using: <source filename>` from `conversation.source_file_name`, not from a global selected file.

## Double Click Handling

The source mutation endpoint refuses changing an already-bound conversation, so accidental duplicate clicks cannot alter the old chat. The frontend creates a new source-bound chat for a different file instead of mutating the existing one.
