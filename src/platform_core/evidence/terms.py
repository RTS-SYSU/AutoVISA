"""Reviewed Rocq constructors for propositions and proof submissions."""

import re


class Rejected(ValueError):
    """Carry a stable diagnostic code and a readable explanation to the evidence service.

    @ivar code Machine-readable outcome used in receipts and history queries.
    """
    def __init__(self, code, detail):
        """Construct a rejected submission or integrity failure.

        @param code Stable diagnostic identifier such as target_mismatch or missing_artifact.
        @param detail Explanation retained as the exception message.
        """
        super().__init__(detail)
        self.code = code


# Importing Target to name its proposition must never grant a proof of it.
#: Statement aliases mapped to terms of type Prop in the reviewed environment.
PROPOSITIONS = {
    "smoke": "AutoRTA.SmokeTarget.smoke_target",
    "case11": "AutoRTA.Target.case11_fig3_acceptance_soundness_int_v1",
    "true": "True", "false": "False",
}
#: Proof aliases mapped to (Rocq term, documented type, owning library module).
SYMBOLS = {
    "add_zero_right": ("Nat.add_0_r", "forall n : nat, n + 0 = n", "Stdlib.Arith.PeanoNat"),
    "truth": ("I", "True", "Corelib.Init.Logic"),
    "pair": ("@conj", "forall A B : Prop, A -> B -> A /\\ B", "Corelib.Init.Logic"),
    "nat_refl": ("(@eq_refl nat)", "forall n : nat, n = n", "Corelib.Init.Logic"),
}


def form(value):
    """Render a reviewed proposition expression as Rocq syntax.

    @param value A known proposition name, binary conjunction or bounded natural equality.
    @return Rocq text representing exactly the supplied proposition.
    @raise Rejected If any constructor, operand shape or numeric literal is unsupported.
    """
    if isinstance(value, str) and value in PROPOSITIONS:
        return PROPOSITIONS[value]
    if isinstance(value, dict) and len(value) == 1:
        # key selects the connective; pair contains its two subformulas or its two natural literals.
        key, pair = next(iter(value.items()))
        if key == "analysis":
            from platform_core.reasoning.statements import render
            return render(pair)
        if key == "and" and isinstance(pair, list) and len(pair) == 2:
            return f"({form(pair[0])} /\\ {form(pair[1])})"
        if key == "eq_nat" and isinstance(pair, list) and len(pair) == 2:
            if all(type(n) is int and 0 <= n <= 1000 for n in pair):
                return f"({pair[0]} = {pair[1]} :> nat)"
    raise Rejected("invalid_statement", f"Unsupported proposition: {value!r}")


def term(value, scope=()):
    """Render a structured proof term using only reviewed constants and bound variables.

    @param value Single-constructor proof expression, such as a symbol, application or lambda.
    @param scope Names already bound by enclosing lambdas, in outermost-first order.
    @return Rocq text for the term with validated binders and parenthesized applications.
    @raise Rejected If a symbol is unapproved, a variable is unbound or a constructor is malformed.
    """
    if not isinstance(value, dict) or len(value) != 1:
        raise Rejected("invalid_term", "Expected one proof-term constructor")
    # key selects the term constructor; arg is its name, literal, operand list or binder triple.
    key, arg = next(iter(value.items()))
    if key == "derivation":
        from platform_core.reasoning.rules import proof
        return proof(arg)
    if key == "symbol":
        if isinstance(arg, str) and arg in SYMBOLS:
            return SYMBOLS[arg][0]
        raise Rejected("unapproved_symbol", repr(arg))
    if key == "prop":
        return form(arg)
    if key == "nat" and type(arg) is int and 0 <= arg <= 1000:
        return str(arg)
    if key == "var" and isinstance(arg, str) and arg in scope:
        return "v_" + arg
    if key == "app" and isinstance(arg, list) and len(arg) >= 2:
        return "(" + " ".join(term(t, scope) for t in arg) + ")"
    if key == "lambda" and isinstance(arg, list) and len(arg) == 3:
        # The binder name enters scope only in body. Its type is a separate proposition expression.
        name, typ, body = arg
        if isinstance(name, str) and re.fullmatch("[a-z][a-z0-9_]{0,30}", name) and name not in scope:
            return f"(fun (v_{name} : {form(typ)}) => {term(body, (*scope, name))})"
    raise Rejected("invalid_term", f"Invalid or unbound {key!r}")


def scoped(assumptions, conclusion):
    """Bind ordered assumptions into the type checked for a conclusion.

    @param assumptions Proposition expressions, starting with the outermost premise.
    @param conclusion Already-rendered Rocq conclusion supplied by the trusted caller.
    @return Implication chain, or the conclusion alone when the assumption list is empty.
    @raise Rejected If an assumption cannot be rendered by form().
    """
    # Model restrictions remain visible in the theorem type; they are not global axioms.
    return " -> ".join([*(form(a) for a in assumptions), conclusion])


def applying(module, args):
    """Render a reference or application to a checked receipt's exported proof.

    @param module Trusted generated module name exporting the checked constant.
    @param args Already-rendered Rocq terms in the theorem's argument order.
    @return Qualified checked constant applied to the arguments, parenthesized when needed.
    """
    return "(" + " ".join([module + ".checked", *args]) + ")" if args else module + ".checked"
