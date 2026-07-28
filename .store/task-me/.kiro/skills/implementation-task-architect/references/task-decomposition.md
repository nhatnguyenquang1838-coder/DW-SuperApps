# Task Decomposition

Start with this hierarchy when applicable:

- contract or schema;
- data migration;
- core domain behavior;
- persistence or adapter;
- API or event interface;
- consumer integration;
- UI integration;
- tests;
- observability and operational controls.

A task is atomic when it has one primary outcome, one bounded rollback unit, one independently testable result and likely effort within the configured maximum.

Mandatory split signals:

- different repository or deployable;
- independent migration;
- independent contract publication;
- different primary owner;
- independently testable outcomes;
- effort exceeds configured maximum;
- incompatible rollback boundaries.

Do not create artificial layer tasks when the result cannot be independently reviewed or validated.
