# Folders

## Overview

- **Folders**: Create/delete folders and move papers between folders.

## Database Changes

- New table: `folders`
  - `id`, `name`, `parent_id` (optional), timestamps
- New column: `papers.folder_id` (nullable, references `folders.id`)

This repo uses `init_db()` at server startup; it now also applies a small, safe migration to add the new table/column.

## UI Usage

- **Create folder**: Click `New folder` in the Library card.
- **Filter by folder**: Click a folder in the folder list (`All papers` / `Unfiled` / created folders).
- **Move a paper**
  - Drag a paper row and drop it onto a folder (or `Unfiled`)
  - Or click `Move` on a paper row and choose a destination
  - Or use the folder dropdown in `Details`

## Deleting Folders

- Deleting a folder deletes its subfolders.
- Papers inside deleted folders are moved to `Unfiled` (`folder_id = null`).
