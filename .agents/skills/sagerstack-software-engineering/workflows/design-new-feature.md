# Workflow: Design New Feature

<required_reading>
**Read these reference files NOW before designing:**
1. references/clean-architecture.md
2. references/ddd-patterns.md
3. references/project-structures.md
4. references/naming-conventions.md
</required_reading>

<process>
## Step 1: Identify the Bounded Context

Ask:
- What domain concept does this feature belong to?
- Does it fit an existing slice or need a new one?
- What are the core entities involved?

**If new slice needed:**
- Create new directory: `src/{sliceName}/`
- Follow vertical slice structure: domain/, application/, infrastructure/, api/

**If existing slice:**
- Identify which layer changes are needed
- Check for any cross-slice dependencies

## Step 2: Design the Domain Model

Start with the domain layer (inside-out approach):

**Identify Value Objects:**
```python
# What concepts need validation/immutability?
@dataclass(frozen=True)
class {ConceptName}:
    value: str

    def __post_init__(self) -> None:
        # Validation rules
        if not self.value:
            raise Invalid{ConceptName}Error()
```

**Identify Entities:**
```python
# What has identity that persists over time?
@dataclass
class {EntityName}:
    id: {EntityName}Id
    # ... other fields

    def {businessOperation}(self) -> None:
        # Business rules here
        pass
```

**Identify Aggregates:**
```python
# What is the consistency boundary?
# What is the root entity that controls access?
@dataclass
class {AggregateName}:
    id: {AggregateName}Id
    # Child entities accessed through root
    items: list[{ChildEntity}] = field(default_factory=list)

    def add{Child}(self, ...) -> None:
        # All modifications through root
        pass
```

## Step 3: Define Domain Events

What significant things happen that other parts of the system care about?

```python
@dataclass(frozen=True)
class {AggregateName}{Action}:  # Past tense
    {aggregateName}Id: str
    occurredAt: datetime = field(default_factory=datetime.utcnow)
```

## Step 4: Define Repository Interface

```python
# src/{slice}/domain/repository.py
from abc import ABC, abstractmethod

class {AggregateName}Repository(ABC):
    @abstractmethod
    def save(self, entity: {AggregateName}) -> None:
        raise NotImplementedError()

    @abstractmethod
    def getById(self, id: {AggregateName}Id) -> {AggregateName} | None:
        raise NotImplementedError()
```

## Step 5: Design Application Layer

**Commands (write operations):**
```python
@dataclass
class {Action}{AggregateName}Command:
    {aggregateName}Id: str
    # ... other required data

class {Action}{AggregateName}Handler:
    def __init__(self, repo: {AggregateName}Repository, eventBus: EventBus):
        self._repo = repo
        self._eventBus = eventBus

    def handle(self, command: {Action}{AggregateName}Command) -> Result[{AggregateName}]:
        # Orchestration logic
        pass
```

**Queries (read operations):**
```python
@dataclass
class Get{AggregateName}Query:
    {aggregateName}Id: str

class Get{AggregateName}Handler:
    def handle(self, query: Get{AggregateName}Query) -> Result[{AggregateName}]:
        pass
```

## Step 6: Plan Infrastructure

**Repository implementation:**
- SQLAlchemy models in `infrastructure/models.py`
- Mapper in `infrastructure/mappers.py`
- Repository in `infrastructure/sqlalchemyRepo.py`

**External integrations:**
- API clients in `infrastructure/{serviceName}Client.py`

## Step 7: Plan API Layer

**Routes:**
```python
# src/{slice}/api/routes.py
router = APIRouter()

@router.post("/", response_model={AggregateName}Response)
def create{AggregateName}(request: Create{AggregateName}Request, handler = Depends(...)):
    pass

@router.get("/{id}", response_model={AggregateName}Response)
def get{AggregateName}(id: str, handler = Depends(...)):
    pass
```

**Schemas:**
```python
# src/{slice}/api/schemas.py
class Create{AggregateName}Request(BaseModel):
    # Request fields

class {AggregateName}Response(BaseModel):
    # Response fields

    @classmethod
    def fromDomain(cls, entity: {AggregateName}) -> "{AggregateName}Response":
        pass
```

## Step 8: Verify Design

Checklist:
- [ ] Domain layer has no infrastructure imports
- [ ] Business logic is in domain layer
- [ ] Value Objects used instead of primitives
- [ ] Repository interface in domain, implementation in infrastructure
- [ ] CamelCase naming throughout
- [ ] Custom exceptions for domain errors
- [ ] Result pattern in application layer
</process>

<output_format>
## Design Document Structure

Present your design as:

```markdown
## Feature: {Feature Name}

### Bounded Context
- Slice: {existing or new slice name}
- Related slices: {any cross-slice dependencies}

### Domain Model

**Value Objects:**
- {Name}: {purpose}

**Entities:**
- {Name}: {purpose, key behaviors}

**Aggregates:**
- {Name}: {root entity, consistency boundary}

**Domain Events:**
- {Name}: {when emitted, who cares}

### Application Layer

**Commands:**
- {CommandName}: {what it does}

**Queries:**
- {QueryName}: {what it returns}

### Infrastructure

**Repository:** {implementation approach}
**External APIs:** {if any}

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /{slice} | Create |
| GET | /{slice}/{id} | Get by ID |

### File Structure

```
src/{slice}/
├── domain/
│   ├── {aggregate}.py
│   ├── {valueObject}.py
│   ├── events.py
│   ├── repository.py
│   └── exceptions.py
├── application/
│   ├── {command}Handler.py
│   └── {query}Handler.py
├── infrastructure/
│   ├── models.py
│   ├── mappers.py
│   └── sqlalchemyRepo.py
└── api/
    ├── routes.py
    ├── schemas.py
    └── dependencies.py
```
```
</output_format>

<success_criteria>
Design is complete when:
- [ ] Bounded context identified
- [ ] Domain model designed (VOs, Entities, Aggregates)
- [ ] Repository interface defined
- [ ] Application layer handlers planned
- [ ] API endpoints specified
- [ ] File structure documented
- [ ] No domain layer dependencies on infrastructure
- [ ] CamelCase naming throughout
</success_criteria>
