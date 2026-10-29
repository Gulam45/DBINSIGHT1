# INSIGHTSQL Mermaid Diagram Reference

> **Status:** The system, component, and data-flow diagrams describe the implemented local application architecture. The deployment diagram remains a proposed local/CI layout, not a production hosting design.

This reference collects the system architecture, component, data flow, and deployment diagrams. Related detail is in [architecture.md](./architecture.md), [component_diagram.md](./component_diagram.md), and [data_flow_diagram.md](./data_flow_diagram.md).

## A. System architecture diagram

```mermaid
flowchart LR
    User[User]
    subgraph Presentation["Presentation layer"]
        Streamlit[Streamlit UI and dashboard]
    end
    subgraph Application["Application and service layer - Python"]
        Request[Input validation]
        Orchestrator[Insights service]
        Context[Schema and context service]
        Validator[SQL parser and policy validator]
        Results[Result limiter and formatter]
        Exceptions[Exception mapping]
        Logging[Logging configuration]
    end
    subgraph AI["AI integration layer - optional"]
        GPT[OpenAI GPT API]
    end
    subgraph DataAccess["Database access layer - Python sqlite3"]
        Repository[Read-only query repository]
    end
    subgraph Persistence["Persistence layer"]
        SQLite[(SQLite database)]
    end
    Tests[Pytest suite]

    User --> Streamlit
    Streamlit --> Request
    Request --> Orchestrator
    Orchestrator --> Context
    Context --> Repository
    Repository --> SQLite
    Orchestrator --> GPT
    GPT --> Validator
    Validator --> Repository
    Repository --> Results
    Results --> Orchestrator
    Orchestrator --> Streamlit
    Exceptions -. handles failures .-> Orchestrator
    Logging -. records redacted events .-> Orchestrator
    Tests -. tests boundaries .-> Streamlit
    Tests -. tests boundaries .-> Orchestrator
    Tests -. tests boundaries .-> Validator
    Tests -. tests boundaries .-> Repository
```

## B. Component diagram

```mermaid
flowchart TB
    User[User]
    subgraph UI["Presentation - Streamlit"]
        Page[Streamlit page and workflow coordinator]
        Input[Question form and validation feedback]
        Examples[Reviewed examples and history controls]
        Table[Bounded result table and CSV download]
        Status[Validation status and safe errors]
    end
    subgraph Services["Python application and service layer"]
        Controller[Streamlit workflow coordinator]
        InputValidator[Request validator]
        SchemaService[Schema context provider]
        QueryService[QueryService]
        History[HistoryService]
        Errors[Typed application errors]
    end
    subgraph SQLControls["SQL generation and validation"]
        PromptBuilder[Prompt builder - metadata only]
        GPTAdapter[OpenAI API adapter]
        Templates[Application-authored reporting templates]
        Validator[SQLGlot parser and policy]
        Approved[ApprovedQuery representation]
    end
    subgraph DBLayer["Database access - Python sqlite3"]
        ReadOnlyDB[ReadOnlyDatabase - authorizer, deadline, and result limits]
    end
    SQLite[(Configured source SQLite file)]
    HistoryDB[(Separate local history SQLite file)]
    Logs[Python logging and redaction]
    Tests[Pytest unit and integration tests]

    User --> Page
    Page --> Input
    Page --> Examples
    Page --> Table
    Page --> Status
    Input --> InputValidator
    InputValidator --> Controller
    Controller --> SchemaService
    SchemaService -->|Read-only schema metadata| SQLite
    Controller --> PromptBuilder
    PromptBuilder --> GPTAdapter
    GPTAdapter -->|Untrusted SQL suggestion| Controller
    Templates --> Controller
    Controller --> QueryService
    QueryService --> Validator
    Validator -->|Accepted query only| Approved
    Approved --> ReadOnlyDB
    ReadOnlyDB -->|Read-only query| SQLite
    ReadOnlyDB -->|Bounded result| QueryService
    QueryService --> History
    History --> HistoryDB
    Controller --> Page
    QueryService -. typed failures .-> Errors
    Errors -. safe user messages .-> Page
    Logs -. redacted events .-> Controller
    Logs -. redacted events .-> QueryService
    Logs -. redacted events .-> ReadOnlyDB
    Tests -. service tests .-> QueryService
    Tests -. policy tests .-> Validator
    Tests -. temporary database tests .-> ReadOnlyDB
```

## C. Data flow diagram

```mermaid
flowchart TD
    Start([User submits natural-language question])
    UI[Streamlit receives request]
    Check{Input valid and within limits?}
    RejectInput[Show safe validation message]
    Service[Python insights service]
    Schema[Retrieve live schema metadata and relationships]
    SchemaOK{Schema retrieval succeeded?}
    DbSchemaError[Log database error; show safe data-source message]
    NeedAI{AI SQL suggestion requested?}
    Prompt[Build minimized prompt from question and schema]
    GPT[OpenAI GPT proposes SQL]
    GPTOK{API response received and parsed?}
    AIError[Log redacted provider failure; report AI assistance unavailable]
    Template[Select an application-authored reporting template]
    SQLValidator[Parse and validate exactly one read-only SQL statement]
    SQLOK{SQL policy accepts query?}
    RejectSQL[Reject SQL; log policy outcome; show safe rejection]
    ReadOnly[Open configured SQLite connection in read-only mode]
    Execute[Execute approved query with deadline and row limit]
    QueryOK{Execution succeeded?}
    QueryError[Close resources; log database or timeout error; show safe query failure]
    Format[Check result size and format bounded rows]
    Display[Streamlit displays candidate SQL, validation, results, and truncation status]
    End([Request complete])

    Start --> UI --> Check
    Check -->|No| RejectInput --> End
    Check -->|Yes| Service --> Schema --> SchemaOK
    SchemaOK -->|No| DbSchemaError --> End
    SchemaOK -->|Yes| NeedAI
    NeedAI -->|Yes| Prompt --> GPT --> GPTOK
    GPTOK -->|No| AIError
    AIError --> End
    GPTOK -->|Yes| SQLValidator
    NeedAI -->|No| Template --> SQLValidator
    SQLValidator --> SQLOK
    SQLOK -->|No: invalid, destructive, multiple, or disallowed SQL| RejectSQL --> End
    SQLOK -->|Yes| ReadOnly --> Execute --> QueryOK
    QueryOK -->|No: SQLite error or deadline| QueryError --> End
    QueryOK -->|Yes| Format --> Display
    Display --> End
```

Post-query AI result explanation is a proposed future feature, not part of the current application flow. The current implementation does not send query results to the provider. A generated candidate is executed automatically only after validation succeeds; reviewed examples are loaded and executed separately.

## D. Deployment diagram

```mermaid
flowchart LR
    subgraph Workstation["User workstation - proposed local deployment"]
        Browser[Local browser]
        subgraph AppProcess["Python process"]
            Streamlit[Streamlit server]
            Service[Python service layer]
            Validator[SQL policy validator]
            SqliteAdapter[sqlite3 read-only adapter]
            Config[Environment configuration]
            Logs[Console or optional rotating logs]
        end
        EnvFile[Local .env - ignored by Git]
        DB[(Configured SQLite file\ninitially DBINSIGHT dbinsight.db)]
    end
    subgraph External["External service"]
        OpenAI[OpenAI GPT API over HTTPS]
    end
    subgraph Quality["Development and CI"]
        Pytest[Pytest]
        TempDB[(Temporary test SQLite database)]
        Mock[Mock OpenAI client]
    end

    Browser -->|localhost| Streamlit
    Streamlit --> Service
    Service --> Validator
    Validator --> SqliteAdapter
    SqliteAdapter -->|read-only| DB
    Config --> Streamlit
    EnvFile -. local configuration .-> Config
    Service -->|minimized context over HTTPS| OpenAI
    Service --> Logs
    Pytest --> Service
    Pytest --> Validator
    Pytest --> TempDB
    Pytest --> Mock
```

The deployment diagram depicts a proposed single-user local setup. A hosted or multi-user deployment requires additional authentication, authorization, managed secrets, data-access governance, and operational controls.
