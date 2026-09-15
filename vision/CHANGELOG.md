# Change Log

## [1.2.10] - 2026-09-15

- Fixed `vision: 이 파일 설명해줘` : from Abs path to relativePath

## [1.2.9] - 2026-09-14

## [1.2.8] - 2026-09-14

## [1.2.7] - 2026-09-14

- Fixed chat command `/ragonly` (done)

## [1.2.6] - 2026-09-14 <abort>

- Fixed chat command `/ragonly` 

## [1.2.5] - 2026-09-14

- Fixed chat command `/ragonly`.

## [1.2.4] - 2026-09-14

- Fixed the dependency graph webview's initial position and prevented its position from resetting whenever it is opened.

## [1.2.3] - 2026-09-11

- Fixed a missing `gitService.onDidRepositoryReady` event connection.

## [1.2.2] - 2026-09-11

- Fixed briefing status checking and display behavior.

## [1.2.1] - 2026-09-11

- Simplified Git Extension integration and removed unused files.
- Simplified behavior when no Git repository is available.

## [1.1.2] - 2026-09-11

- Fixed extension shutdown state handling by deactivating the current project correctly.

## [1.0.3] - 2026-09-10

- Packaging and release metadata update.

## [1.0.2] - 2026-09-10

- Added a confirmation alert to verify briefing creation when requesting indexing.
- Fixed RAG-only chat behavior.
- Fixed briefing status handling during indexing.

## [1.0.0] - 2026-09-09

- Added project and commit briefing status handling, including stale-briefing indicators.
- Added indexing requests from the extension, with controls shown only when indexing or briefing generation is needed.
- Added support for selecting server-indexed projects and keeping chat, briefing, and indexing configuration consistent.
- Added commit SHA comparison so the briefing for the current commit is loaded.
- Added project and branch identifiers to chat, briefing, and indexing requests.
- Updated the README and removed unused package features.
