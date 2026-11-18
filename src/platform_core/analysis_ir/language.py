"""A small typed Analysis IR whose renderer never accepts arbitrary Rocq source strings."""

import re


class MappingFailure(ValueError):
    """Carry a stable mapping diagnostic.

    @ivar code Machine-readable reason why mapping or checking failed.
    """

    def __init__(self, code, message):
        """Retain mapping failure details.

        @param code Stable diagnostic identifier.
        @param message Human-readable explanation.
        """
        super().__init__(message)
        self.code = code


#: Supported sorts and their fixed Rocq representations.
SORTS = {"Nat":"nat", "Task":"Task", "TaskSet":"TaskSet", "Arrivals":"Arrivals",
         "Schedule":"Schedule", "Prop":"Prop", "OptionTask":"option Task", "Job":"Job", "OptionJob":"option Job"}
#: Reviewed kernel definitions; signatures prevent arity and sort confusion.
SYMBOLS = {
    "cost": (["Task"], "Nat", "task_cost"),
    "deadline": (["Task"], "Nat", "task_deadline"),
    "period": (["Task"], "Nat", "task_period"),
    "prefix": (["Nat","TaskSet"], "TaskSet", "firstn"),
    "lookup": (["TaskSet","Nat"], "OptionTask", "nth_error"),
    "some_task": (["Task"], "OptionTask", "(@Some Task)"),
    "taskset_wf": (["TaskSet"], "Prop", "taskset_wf"),
    "legal_arrivals": (["TaskSet","Arrivals"], "Prop", "legal_arrivals"),
    "bounded_demands": (["TaskSet","Arrivals"], "Prop", "bounded_demands"),
    "valid_dm_schedule": (["Arrivals","Schedule"], "Prop", "valid_dm_schedule"),
    "deadlines_met": (["TaskSet","Arrivals","Schedule"], "Prop", "all_deadlines_met"),
    "accepts_from": (["TaskSet","Task","Nat"], "Prop", "accepts_from"),
}


def identifier(value):
    """Accept only ordinary, nonreserved generated identifiers.

    @param value Candidate binder or generated definition name.
    @return Validated identifier.
    @raise MappingFailure If the name could introduce source syntax or shadow keywords.
    """
    if not isinstance(value, str) or not re.fullmatch("[a-z][a-z0-9_]*", value) or value in {"fun","forall","match","end","let","in","fix","as","return","with"}:
        raise MappingFailure("invalid_ir", "Invalid identifier")
    return value


def expression(tree, environment, signatures):
    """Type-check and render one expression in a known variable scope.

    @param tree Tagged expression dictionary.
    @param environment Variable-to-sort bindings available at this location.
    @param signatures Approved function signatures and Rocq names.
    @return Pair of inferred sort and generated Rocq expression.
    @raise MappingFailure If the tree, binding, sort or application is invalid.
    """
    # shape enforces exact keys so ignored annotations cannot hide semantic changes.
    def shape(*keys):
        """Require the exact constructor fields.

        @param keys Fields expected in addition to op.
        @raise MappingFailure If the constructor shape differs.
        """
        if set(tree) != {"op", *keys}:
            raise MappingFailure("invalid_ir", "Unexpected expression fields")

    if not isinstance(tree, dict) or "op" not in tree:
        raise MappingFailure("invalid_ir", "Expected a tagged expression")
    # @var op Validated constructor selecting one typed rendering rule.
    op = tree["op"]
    if op == "var":
        shape("name")
        # @var name Source-safe identifier resolved in the current lexical scope.
        name = identifier(tree["name"])
        if name not in environment:
            raise MappingFailure("unbound_variable", name)
        return environment[name], name
    if op == "nat":
        shape("value")
        # @var value Small natural literal; booleans and negative integers are excluded.
        value = tree["value"]
        if type(value) is not int or not 0 <= value <= 1000:
            raise MappingFailure("invalid_ir", "Invalid natural literal")
        return "Nat", str(value)
    if op == "call":
        shape("symbol", "args")
        # @var signature Approved argument sorts, result sort and Rocq symbol.
        signature = signatures.get(identifier(tree["symbol"]))
        if signature is None or not isinstance(tree["args"], list):
            raise MappingFailure("invalid_ir", "Unknown function")
        # @var arguments Ordered (sort, source) pairs checked against the signature.
        arguments = [expression(arg, environment, signatures) for arg in tree["args"]]
        if [sort for sort, _ in arguments] != signature[0]:
            raise MappingFailure("sort_mismatch", tree["symbol"])
        return signature[1], "(" + " ".join([signature[2], *(text for _, text in arguments)]) + ")"
    if op in ("add","sub","mul","div","min","le","lt","eq","implies","and"):
        shape("left","right")
        # @var left, right Recursively checked operand sorts and rendered terms.
        left, right = [expression(tree[key], environment, signatures) for key in ("left","right")]
        # @var expected Required common operand sort except for polymorphic equality.
        expected = "Prop" if op in ("implies","and") else "Nat"
        if (left[0] != right[0]) or (op != "eq" and left[0] != expected):
            raise MappingFailure("sort_mismatch", op)
        # @var token Fixed operator spelling; no user text is interpolated as syntax.
        token = {"add":"+","sub":"-","mul":"*","div":"/","min":"Nat.min","le":"<=","lt":"<","eq":"=","implies":"->","and":"/\\"}[op]
        # @var text Parenthesized expression preserving IR evaluation order.
        text = f"(Nat.min {left[1]} {right[1]})" if op == "min" else f"({left[1]} {token} {right[1]})"
        return ("Prop" if op in ("le","lt","eq","implies","and") else "Nat"), text
    if op in ("forall","exists","sum"):
        shape(*(("name","sort","body") if op in ("forall","exists") else ("name","over","seed","body")))
        # @var name Source-safe identifier resolved in the current lexical scope.
        name = identifier(tree["name"])
        # @var sort Bound variable sort; finite sums always bind a task.
        sort = tree["sort"] if op in ("forall","exists") else "Task"
        if name in environment or sort not in SORTS or sort == "Prop":
            raise MappingFailure("invalid_binder", name)
        # @var child_sort, body Type and source under the extended lexical environment.
        child_sort, body = expression(tree["body"], {**environment, name:sort}, signatures)
        if op in ("forall","exists"):
            if child_sort != "Prop":
                raise MappingFailure("sort_mismatch", "Quantifier body must be Prop")
            return "Prop", f"({op} ({name} : {SORTS[sort]}), {body})"
        # @var over, seed Task collection and natural initial accumulator.
        over, seed = [expression(tree[key], environment, signatures) for key in ("over","seed")]
        if (over[0], seed[0], child_sort) != ("TaskSet","Nat","Nat"):
            raise MappingFailure("sort_mismatch", "Sum requires tasks and natural costs")
        # The generated accumulator uses a reserved uppercase name unavailable to input binders.
        return "Nat", f"(fold_right (fun ({name} : Task) (Acc : nat) => {body} + Acc) {seed[1]} {over[1]})"
    raise MappingFailure("invalid_ir", str(op))


def source(ir):
    """Generate typed definitions and correspondence checks from a prepared IR.

    @param ir Analysis IR containing ordered definitions and the supported goal.
    @return Rocq source with explicit binders, executable formulas and a goal proposition.
    @raise MappingFailure If definitions or goals violate the typed language.
    """
    # @var signatures Local symbol table extended only after each definition is checked.
    signatures = dict(SYMBOLS)
    # @var lines Complete source emitted in dependency order.
    lines = ["From Stdlib Require Import Arith.PeanoNat Lists.List.",
             "From AutoRTA Require Import Model Analysis Target.", "",
             "(** Generated from a frozen review revision. No scheduling theorem is proved here. *)"]
    # @var definition Ordered typed algorithm definition with semantic source keys.
    for definition in ir["definitions"]:
        # @var name, parameters Definition identity and ordered typed arguments.
        name = identifier(definition["name"])
        parameters = definition["parameters"]
        # @var environment Lexical variable scope for this definition only.
        environment = {}
        for parameter, sort in parameters:
            identifier(parameter)
            if parameter in environment or sort not in SORTS or sort == "Prop":
                raise MappingFailure("invalid_binder", parameter)
            environment[parameter] = sort
        if name in signatures:
            raise MappingFailure("invalid_ir", "Duplicate definition")
        # @var sort, text Inferred result type and checked generated expression.
        sort, text = expression(definition["body"], environment, signatures)
        if sort != definition["result"]:
            raise MappingFailure("sort_mismatch", name)
        signatures[name] = ([sort for _, sort in parameters], sort, name)
        # Parameter and result strings come exclusively from the finite sort table.
        binders = " ".join(f"({parameter} : {SORTS[typ]})" for parameter, typ in parameters)
        # @var documentation English API comments carried into generated Rocq files.
        documentation = [f"(** {name}: typed expression with exact source bindings in analysis-ir.json."]
        documentation.extend(f"    @param {parameter} Bound {typ} input; mathematical role follows the frozen IR." for parameter, typ in parameters)
        documentation.append(f"    @return A value of sort {sort}. *)")
        lines.extend(["\n".join(documentation),
                      f"Definition {name} {binders} : {SORTS[sort]} := {text}.", ""])
    # @var goal Supported target retained alongside any explicitly blocked goals.
    goal = next((goal for goal in ir["goals"] if goal["status"] == "mapped"), None)
    if goal is None:
        raise MappingFailure("no_mapped_goal", "No supported goal to encode")
    # @var sort, text Explicit proposition type and fully quantified target expression.
    sort, text = expression(goal["proposition"], {}, signatures)
    if sort != "Prop":
        raise MappingFailure("sort_mismatch", "Goal must be Prop")
    lines.extend(["(** Open proposition: @var ts ranges over task sets, a over arrivals, s over schedules.",
                  "    @return A method-level guarantee; its declaration is not a schedulability proof. *)",
                  "Definition mapped_goal : Prop := " + text + ".",
                  "(** These equalities check translation only, not the truth of mapped_goal. *)",
                  "(** Initial-value correspondence. @param hp Higher-priority prefix. @param p Own task. *)",
                  "Lemma initial_matches : forall hp p, ir_initial hp p = initial hp p. Proof. reflexivity. Qed.",
                  "(** Demand correspondence. @param hp Higher-priority prefix. @param p Own task. @param t Iteration time. *)",
                  "Lemma workload_matches : forall hp p t, ir_workload hp p t = workload hp p t. Proof. reflexivity. Qed.",
                  "(** Acceptance correspondence. @param ts Complete priority-ordered task set. *)",
                  "Lemma acceptance_matches : forall ts, ir_fig3_accepts ts = fig3_accepts ts. Proof. reflexivity. Qed.",
                  "(** Target proposition correspondence. @return Equality of statements, not evidence of their truth. *)",
                  "Lemma target_matches : mapped_goal = case11_fig3_acceptance_soundness_int_v1. Proof. reflexivity. Qed.",
                  "Check mapped_goal : Prop.", ""])
    return "\n".join(lines)
