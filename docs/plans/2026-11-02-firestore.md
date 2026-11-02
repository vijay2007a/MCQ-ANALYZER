# Firebase Authentication and Firestore Migration

Goal: Firebase verifies identity; the backend authorizes administrators and stores all application records in Firestore.

Architecture: Keep existing scoring and API behavior. Introduce a document-backed unit of work implementing the query subset used by services. Persist each record as a Firestore document under a server-only namespace. Use optimistic collection revisions and atomic transactions to reject conflicting writes, including replay and uniqueness conflicts. No local database file in Firestore mode.

1. Add server Firebase configuration and Admin SDK initialization. Use ADC locally and a private service-account environment variable on Vercel. Never use browser config as credentials.
2. Implement document queries, relationships, defaults, atomic writes, uniqueness validation, rollback and conflict handling. Keep SQL mode for existing installations and tests.
3. Verify Firebase ID tokens server-side and require a server-issued admin claim plus a provisioned active admin record. Remove password authentication from the deployed Firebase flow.
4. Switch startup and health to the chosen backend. Add CLI provisioning and explicit SQL-to-Firestore migration without deleting source data.
5. Test cross-session persistence, conflicts, login authorization, quiz import, results and archive/deletion behavior. Run existing regression suite.
6. Deploy only after the project owner grants server access and credentials are configured. Live access is currently denied for project mcq-analyzer-16a47.
