# Architecture

This page gives a simple view of the main warehouse runtime structure and workflows.

## Legend

- Entry point: starts execution.
- Work layer: performs data loading or materialization.
- Support layer: helps a work layer with external reads or cross-source mapping.
- Persistence layer: owns database, schema, and validation.
- Orange solid arrows: orchestration or direct runtime control flow.
- Blue dashed arrows: support-layer calls or helper dependencies.
- Green solid arrows: persistence or warehouse ownership flow.
- Purple dotted arrows: upstream external inputs.

In this repo, `sources` means live API sources only. The SQLite source
databases, `fpl.db` and `understat.db`, are upstream inputs read directly
by `builders` and `integration`.

## System Boundaries

This diagram shows external inputs, package boundaries, and where data ends up.
It does not define implementation construction rules or the canonical materialization sequence.

```mermaid
flowchart LR
	subgraph Upstream Inputs
		direction LR
		FPLDB[fpl.db]
		UDB[understat.db]
		API[FPL API]
	end

	subgraph Warehouse Package
		direction TB
		CLI[cli]
		BUILD[build]
		BUILDERS[builders]
		SOURCES[sources]
		INTEGRATION[integration]
		WAREHOUSE[warehouse]
	end

	subgraph Output
		direction TB
		MASTER[(master.db)]
	end

	CLI --> BUILD
	BUILD --> BUILDERS
	BUILDERS --> INTEGRATION
	BUILDERS --> WAREHOUSE
	WAREHOUSE --> MASTER

	FPLDB --> BUILDERS
	UDB --> BUILDERS
	API --> SOURCES
	SOURCES --> BUILDERS
```

## Execution And Dependency Layout

Execution starts in `cli` or direct calls into `build` and `builders`.
`sources` and `integration` do not start work themselves. They support
the builder layer when external data or cross-source mapping is needed.

This diagram shows runtime call and dependency direction.

```mermaid
flowchart TD
	CLI[cli entrypoint]
	BUILD[build orchestrator]
	BUILDERS[builders]
	SOURCES[sources support layer]
	INTEGRATION[integration support layer]
	WAREHOUSE[warehouse persistence layer]

	CLI -->|full build| BUILD
	CLI -->|targeted commands| BUILDERS
	BUILD -->|orchestrates| BUILDERS
	BUILDERS -->|live API reads when needed| SOURCES
	BUILDERS -->|cross-source mapping| INTEGRATION
	BUILDERS -->|schema, writes, validation| WAREHOUSE
```

## Full Warehouse Build

```mermaid
sequenceDiagram
	participant CLI as cli.main
	participant B as build.build_all
	participant S as warehouse.schema
	participant D as builders.dimensions
	participant F as builders.facts
	participant SN as builders.snapshots
	participant C as warehouse.contracts

	CLI->>B: build warehouse
	B->>S: create_schema()
	B->>D: build_dim_teams()
	B->>D: build_dim_gameweeks()
	B->>D: build_dim_players()
	B->>F: build_fixture_bridge()
	B->>F: build_fact_player_gw()
	B->>F: build_fact_shots()
	B->>F: build_fact_fixtures()
	B->>F: build_fact_match_stats()
	B->>F: enrich_xg_chain_buildup()
	B->>SN: materialize_all_snapshots()
	B->>C: validate_build()
```

## Manager Squad Refresh

This is an optional operational workflow for persisted manager-specific state.
It is not part of the governed warehouse snapshot contract.

```mermaid
sequenceDiagram
	participant CLI as cli.main
	participant M as builders.manager
	participant API as sources.fpl
	participant DB as warehouse.db

	CLI->>DB: _connect_warehouse()
	CLI->>M: build_fact_manager_squad(conn, team_id, gw)
	M->>API: get_picks(team_id, gw)
	API-->>M: picks
	M->>DB: delete existing GW squad
	M->>DB: insert 15 squad rows
```

## Availability Refresh

```mermaid
sequenceDiagram
	participant CLI as cli.main
	participant SN as builders.snapshots
	participant API as sources.fpl
	participant DB as warehouse db

	CLI->>DB: _connect_warehouse()
	CLI->>SN: refresh_player_availability(conn)
	SN->>API: get_bootstrap()
	API-->>SN: elements
	SN->>DB: update dim_players availability fields
```

This refresh path updates live current-state player availability fields only.
Historical warehouse facts remain rebuild-owned and are refreshed through the scheduled source refresh plus full warehouse rebuild path.
