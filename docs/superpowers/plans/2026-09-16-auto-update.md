# Windows automatic update implementation plan

User outcome: one browser button downloads the official release, preserves data and models, restarts the installed program, and reports failures without asking users to overwrite files.

1. Add a standard-library package validator and transactional replacement helper. Reject unsafe archive paths and application data; preserve a rollback copy. Test successful replacement and partial-failure restoration.
2. Add release discovery, verified streaming download, disk checks, progress persistence, and the helper handoff. Only official GitHub assets with matching SHA-256 and size are accepted. Updates require a packaged Windows installation and an idle application. Stop accepting mutations during maintenance.
3. Run a separate one-file helper from the update workspace. Wait for the exact parent process to exit, replace application components, restart with existing port/server options, and verify the target version through health. Roll back and restart the previous application if startup fails.
4. Add browser update progress and restart polling, with clear failure messages. Permit update initiation only from the server PC and reject cross-origin requests. Source checkouts retain the download link instead.
5. Package the helper alongside the application. Run unit, browser, and Windows helper integration tests in isolated directories. Do not modify production data or publish a release as part of verification.

Scope limits: users of versions without the updater must first install an updater-capable release once. Interrupted machine shutdown may require starting the preserved recovery helper; ordinary download, replacement, and new-version startup failures should leave or restore the old application. Backups are retained until a later successful update rather than deleted during the transaction.
