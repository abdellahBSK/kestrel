# Architecture decision records

Short records of decisions that shape the code for longer than one feature. Each one says what
was decided, why, and what it costs. To propose one, copy [`0000-template.md`](0000-template.md)
to the next number and open a pull request.

| # | Decision | Status |
|---|---|---|
| [0001](0001-stdlib-python-server.md) | The server uses the Python standard library only | Accepted |
| [0002](0002-sqlite-event-store.md) | Events are stored in one SQLite file | Accepted |
| [0003](0003-react-typescript-dashboard.md) | The dashboard is React + TypeScript, built into the package | Accepted |
| [0004](0004-server-decides-liveness.md) | The server decides liveness from evidence, at read time | Accepted |
| [0005](0005-utc-api.md) | The API speaks UTC; the browser converts | Accepted |
| [0006](0006-attribution-opt-in.md) | Hiding AI attribution in agent commits is opt-in | Accepted |
