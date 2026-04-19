"""Core data types shared across all layers.

These mirror the JSON Schema definitions in atom.schema.json,
kernel_ast.schema.json, and query_result.schema.json.

All dataclasses are frozen so values can be hashed and compared
structurally; the runtime treats them as immutable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union


# ---------------------------------------------------------------------------
# atom.schema.json
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConstTerm:
    name: str


@dataclass(frozen=True)
class VarTerm:
    name: str


Term = Union[ConstTerm, VarTerm]


@dataclass(frozen=True)
class Atom:
    predicate: str
    args: tuple[Term, ...]


# ---------------------------------------------------------------------------
# kernel_ast.schema.json — model-side statements
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Annotation:
    confidence: float | None = None
    source: str | None = None


@dataclass(frozen=True)
class CauseStatement:
    from_atom: Atom
    to_atom: Atom
    forall: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProbabilityStatement:
    target: Atom
    given: tuple[Atom, ...]
    value: float
    forall: tuple[str, ...] = ()
    annotations: Annotation | None = None


AtomValue = Union[bool, int, float, str]


@dataclass(frozen=True)
class ObservationStatement:
    atom: Atom
    value: AtomValue
    annotations: Annotation | None = None


@dataclass(frozen=True)
class Intervention:
    atom: Atom
    value: AtomValue


# ---------------------------------------------------------------------------
# kernel_ast.schema.json — queries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CauseQuery:
    from_atom: Atom
    to_atom: Atom


@dataclass(frozen=True)
class AssocQuery:
    left: Atom
    right: Atom
    given: tuple[Atom, ...]


@dataclass(frozen=True)
class EffectQuery:
    target: Atom
    intervention: Intervention
    given: tuple[Atom, ...]


@dataclass(frozen=True)
class IdentifyQuery:
    target: Atom
    intervention: Intervention
    given: tuple[Atom, ...]


@dataclass(frozen=True)
class ProbabilityQuery:
    target: Atom
    given: tuple[Atom, ...]


Query = Union[
    CauseQuery,
    AssocQuery,
    EffectQuery,
    IdentifyQuery,
    ProbabilityQuery,
]


@dataclass(frozen=True)
class QueryStatement:
    id: str
    query: Query


Statement = Union[
    CauseStatement,
    ProbabilityStatement,
    ObservationStatement,
    QueryStatement,
]


@dataclass(frozen=True)
class Program:
    version: str
    objects: tuple[str, ...]
    statements: tuple[Statement, ...]
    extensions: dict | None = None


# ---------------------------------------------------------------------------
# query_result.schema.json — formula AST (see formula_ast_spec_v0_1.md)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VarRef:
    name: str


ValueExpr = Union[bool, int, float, str, VarRef]


@dataclass(frozen=True)
class ValuedAtom:
    atom: Atom
    # None means the value is bound externally by the enclosing query
    # context (see formula_ast_spec_v0_1.md §3.3).
    value: ValueExpr | None = None


@dataclass(frozen=True)
class ConstantExpr:
    value: float


@dataclass(frozen=True)
class ProbabilityRefExpr:
    target: ValuedAtom
    given: tuple[ValuedAtom, ...]


@dataclass(frozen=True)
class ProductExpr:
    terms: tuple["FormulaExpr", ...]


@dataclass(frozen=True)
class BindDecl:
    name: str


@dataclass(frozen=True)
class SumExpr:
    bind: BindDecl
    over: Atom
    body: "FormulaExpr"


FormulaExpr = Union[ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr]


# ---------------------------------------------------------------------------
# query_result.schema.json — result envelope
# ---------------------------------------------------------------------------

class ResultStatus(str, Enum):
    STRUCTURALLY_SOLVED = "structurally_solved"
    NUMERICALLY_SOLVED = "numerically_solved"
    NEEDS_INVESTIGATION = "needs_investigation"
    OUTSIDE_LANGUAGE = "outside_language"


class QueryKind(str, Enum):
    CAUSE = "cause"
    ASSOC = "assoc"
    EFFECT = "effect"
    IDENTIFY = "identify"
    PROBABILITY = "probability"


@dataclass(frozen=True)
class StructuralResult:
    value: bool | str | None
    supporting_paths: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class NumericInterval:
    low: float
    high: float


@dataclass(frozen=True)
class NumericResult:
    value: float | None
    interval: NumericInterval | None = None
    unit: str | None = None


class MissingKind(str, Enum):
    PARAMETER = "parameter"
    OBSERVATION = "observation"
    SAMPLE = "sample"
    STRUCTURE = "structure"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class MissingItem:
    kind: MissingKind
    name: str
    priority: Priority
    reason: str | None = None


class InvestigationAction(str, Enum):
    COLLECT_OBSERVATION = "collect_observation"
    RUN_EXPERIMENT = "run_experiment"
    INCREASE_SAMPLE = "increase_sample"
    VALIDATE_PARAMETER = "validate_parameter"


@dataclass(frozen=True)
class InvestigationRequest:
    action: InvestigationAction
    target: str
    priority: Priority
    note: str | None = None


@dataclass(frozen=True)
class QueryResult:
    status: ResultStatus
    query_kind: QueryKind
    query_id: str | None = None
    structural_result: StructuralResult | None = None
    numeric_result: NumericResult | None = None
    confidence: float | None = None
    formula: FormulaExpr | None = None
    missing_information: tuple[MissingItem, ...] = ()
    investigation_requests: tuple[InvestigationRequest, ...] = ()
    explanation: str | None = None
    extensions: dict | None = None
