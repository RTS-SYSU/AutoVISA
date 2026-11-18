"""The public boundary for revisions, checks and evidence-history queries."""

from .terms import Rejected, applying, form, scoped, term

#: Only these recorded outcomes can supply evidence after freshness and integrity checks.
ACCEPTED = {"conditional", "complete"}


class Evidence:
    """Manage frozen goals, proof attempts and the current usability of their evidence.

    @ivar db Ledger storing revisions and attempts and resolving their artifact manifests.
    @ivar checker Rocq session whose environment profile is pinned by each context.
    """
    def __init__(self, ledger, checker):
        """Bind the ledger and checker used by this service instance.

        @param ledger Ledger providing revision history and immutable evidence objects.
        @param checker Configured checker for the current model build and environment.
        """
        self.db, self.checker = ledger, checker

    def context(self, name, hypotheses=(), parent=None, note=""):
        """Append a context revision containing the current environment and model hypotheses.

        @param name Logical context name shared by its revisions.
        @param hypotheses Ordered proposition expressions to bind as explicit theorem premises.
        @param parent Expected current context revision ID, or None on the first revision.
        @param note Human-readable explanation stored as part of this revision.
        @return Immutable context revision ID.
        @raise Rejected If a hypothesis is unsupported or the supplied parent is out of date.
        """
        return self.db.revise("context", name, {"profile": self.checker.profile_id,
                              "hypotheses": list(hypotheses), "note": note}, parent)

    def goal(self, name, context, proposition, parent=None):
        """Append a target proposition tied to a specific context revision.

        @param name Logical goal name used for subsequent history queries.
        @param context Exact context revision ID that supplies the hypotheses and environment.
        @param proposition Statement in the reviewed input language.
        @param parent Expected current goal revision ID, or None for a new goal.
        @return Immutable goal revision ID.
        @raise Rejected If the proposition, context or parent cannot be accepted.
        """
        return self.db.revise("goal", name, {"proposition": proposition}, parent, context)

    def prove(self, target, proof, premises=()):
        """Check a structured proof for a goal, optionally under additional open premises.

        @param target Exact goal revision to check.
        @param proof Structured proof term, or an explicit obligation to submit for audit.
        @param premises Ordered goal revision IDs treated as premises of the conditional proof.
        @return Attempt ID for retrieving either the checker receipt or its rejection diagnostic.
        @raise Rejected If the target cannot be registered as a goal attempt.
        """
        return self._submit(target, {"kind": "proof", "term": proof, "premises": list(premises)})

    def compose(self, target, rule, proofs):
        """Apply a checked conditional proof to complete proofs of its ordered premises.

        @param target Goal revision the application must establish.
        @param rule Attempt ID of the conditional receipt for this exact target.
        @param proofs Complete-proof attempt IDs in the rule's original premise order.
        @return New attempt ID, including when an input is rejected during checking.
        @raise Rejected If the target cannot be registered as a goal attempt.
        """
        return self._submit(target, {"kind": "application", "rule": rule, "proofs": list(proofs)})

    def assess(self, attempt):
        """Assess a saved receipt against the active checker and its full dependency history.

        @param attempt Existing proof-attempt identity; no new proof is submitted.
        @return Exact target, context, outcome and reasons the receipt cannot be reused.
        """
        # @var saved, revision Verified receipt index and its exact goal-context binding.
        saved = self.db.attempt(attempt)
        revision = self.db.revision(saved["target"])
        issues = self._issues(saved,{})
        if saved["code"] not in ACCEPTED:
            issues.append({"code":"proof_not_accepted","detail":saved["code"]})
        return {"attempt":attempt,"target":saved["target"],"context":revision["context"],
                "outcome":saved["code"],"issues":issues,"usable":not issues}

    def _revision_issues(self, target):
        """Compare a goal and its frozen context against their current heads and environment.

        @param target Goal revision ID being assessed.
        @return List of changes with reason codes and the previous and current identities.
        @raise Rejected If a referenced revision is missing.
        """
        # rev and ctx are pinned records; head is the newest revision for each logical name.
        rev = self.db.revision(target)
        ctx = self.db.revision(rev["context"])
        issues = []
        for obj in (rev, ctx):
            head = self.db.current(obj["id"])
            if head != obj["id"]:
                issues.append({"code": obj["kind"] + "_revised", "name": obj["name"],
                               "was": obj["id"], "now": head})
        if ctx["body"]["profile"] != self.checker.profile_id:
            issues.append({"code": "environment_changed", "was": ctx["body"]["profile"],
                           "now": self.checker.profile_id})
        return issues

    def _issues(self, att, cache):
        """Find integrity and freshness problems inherited by this attempt.

        @param att Attempt row, including the frozen request and any recorded outcome.
        @param cache Per-query or per-submission mapping of attempt IDs to previously computed issues.
        @return Reasons this attempt or a prerequisite is unusable, including dependency paths.
        """
        # A conditional receipt also pins the revisions of its as-yet unproved premises.
        # A composed receipt inherits those pins transitively, even across several layers.
        # key identifies the attempt across every branch that may share it as a prerequisite.
        key = att["id"]
        if key in cache:
            return cache[key]
        # req records whether this receipt pins open premise revisions or actual input attempts.
        req = att["request"]
        issues = self._revision_issues(att["target"])
        if att["code"] in ACCEPTED:
            try:
                self.db.manifest(att, verify=True)
            except Rejected as exc:
                issues.append({"code": exc.code, "detail": str(exc)})
            if req["kind"] == "proof":
                for premise in req["premises"]:
                    for reason in self._revision_issues(premise):
                        issues.append({**reason, "premise": premise})
            else:
                for dep in [req["rule"], *req["proofs"]]:
                    for reason in self._issues(self.db.attempt(dep), cache):
                        issues.append({**reason, "via": dep})
        cache[key] = issues
        return issues

    def _input(self, key, expected, target, ctx, cache):
        """Resolve one prerequisite receipt at the exact kind, goal and context required.

        @param key Attempt ID supplied as a dependency.
        @param expected Required outcome code, either conditional or complete.
        @param target Required goal revision ID for this dependency slot.
        @param ctx Required context revision ID.
        @param cache Attempt-issue cache shared across this dependency traversal.
        @return Pair containing the attempt row and its verified artifact manifest.
        @raise Rejected If an input is missing, stale, damaged or belongs to another goal or context.
        """
        att = self.db.attempt(key)
        # actual describes the goal the dependency proved, which may differ from the requested target.
        actual = self.db.revision(att["target"])
        if actual["context"] != ctx:
            raise Rejected("context_mismatch", key + " belongs to " + actual["context"])
        if actual["id"] != target or att["code"] != expected:
            raise Rejected("dependency_mismatch", f"{key}: need {expected} for {target}, "
                           f"got {att['code']} for {actual['id']}")
        issues = self._issues(att, cache)
        if issues:
            raise Rejected(issues[0]["code"], str(issues[0]))
        return att, self.db.manifest(att)

    def _submit(self, target, req):
        """Register a request and persist the checker outcome with its supporting artifacts.

        @param target Frozen goal revision being checked.
        @param req Structured proof or application request, including ordered input identities.
        @return Registered attempt ID for both accepted submissions and recorded rejections.
        @raise Rejected If an attempt cannot be registered or its stored artifacts cannot be committed.
        """
        attempt = self.db.start(target, req)
        ctx = self.db.revision(self.db.revision(target)["context"])
        # hyps contains context assumptions in binder order; goal is the rendered target conclusion.
        hyps = ctx["body"]["hypotheses"]
        goal = form(self.db.revision(target)["body"]["proposition"])
        # m accumulates the receipt even on a rejection, so diagnostics remain tied to this target and profile.
        m = {"attempt": attempt, "target": target, "context": ctx["id"],
             "profile": self.checker.profile_id, "files": dict(self.checker.base["files"]),
             "commands": [], "environment": self.checker.profile}
        # dependencies holds ordered attempt IDs for the ledger's receipt edges after successful composition.
        dependencies = []
        try:
            issues = self._revision_issues(target)
            if issues:
                raise Rejected(issues[0]["code"], str(issues[0]))
            # modules maps required .vo names to hashes; premises holds the proposition at each open rule slot.
            modules, premises = {}, []
            if req["kind"] == "proof":
                for p in req["premises"]:
                    rev = self.db.revision(p)
                    if rev["kind"] != "goal" or rev["context"] != ctx["id"]:
                        raise Rejected("context_mismatch", str(p))
                    if self.db.current(p) != p:
                        raise Rejected("goal_revised", p)
                    premises.append(rev["body"]["proposition"])
                # typ is the full statement the independent wrapper will assign to the submitted term.
                typ = scoped([*hyps, *premises], goal)
                value = req["term"]
                if isinstance(value, dict) and set(value) == {"obligation"}:
                    # An explicit open obligation is representable, but its actual use must fail audit.
                    candidate = f"Axiom unresolved : {form(value['obligation'])}.\nDefinition candidate := unresolved.\n"
                else:
                    candidate = f"Definition candidate := {term(value)}.\n"
                code = "conditional" if premises else "complete"
            else:
                typ, cache = scoped(hyps, goal), {}
                # rule holds the pinned request, rm its compiled artifacts, and wanted the required premise revisions.
                rule, rm = self._input(req["rule"], "conditional", target, ctx["id"], cache)
                wanted = rule["request"]["premises"]
                if len(wanted) != len(req["proofs"]):
                    raise Rejected("missing_premise", f"Need {len(wanted)} proofs in order; got {len(req['proofs'])}")
                # deps holds the rule manifest first, then one verified manifest per premise in application order.
                deps = [rm]
                for revision, key in zip(wanted, req["proofs"]):
                    _, dep = self._input(key, "complete", revision, ctx["id"], cache)
                    deps.append(dep)
                dependencies = [req["rule"], *req["proofs"]]
                for dep in deps:
                    for name, key in dep["modules"].items():
                        if modules.setdefault(name, key) != key:
                            raise Rejected("dependency_mismatch", "Conflicting compiled copies of " + name)
                # Reapply the checked implication to the ordered proof terms in Rocq.
                # Matching database rows alone cannot turn a conditional proof into a complete one.
                # args are the shared context binders forwarded to the rule and to each premise proof.
                args = [f"h{i}" for i in range(len(hyps))]
                value = applying(rm["module"], [*args, *(applying(d["module"], args) for d in deps[1:])])
                for i in reversed(range(len(hyps))):
                    value = f"(fun (h{i} : {form(hyps[i])}) => {value})"
                imports = " ".join(dict.fromkeys(d["module"] for d in deps))
                candidate = f"Require {imports}.\nDefinition candidate := {value}.\n"
                code = "complete"
            m["exact_type"] = typ
            self.checker.check(attempt, typ, candidate, modules, m)
            detail = "Exact type, dependency closure, global assumptions and kernel checked."
        except Rejected as exc:
            code, detail, dependencies = exc.code, str(exc), []
        self.db.finish(attempt, code, detail, m, dependencies)
        return attempt

    def history(self, name):
        """Read the revision history and proof status of a logical goal in one database snapshot.

        @param name Logical goal name shared by all its revisions.
        @return Goal head, proof state, conditional routes, outstanding issues, revisions and attempts.
        @raise Rejected If the goal name is unknown.
        """
        with self.db.snapshot():
            return self._history(name)

    def _history(self, name):
        """Assemble goal history within the read transaction opened by history().

        @param name Logical goal name whose revisions and attempts are collected.
        @return Snapshot data with historic outcomes and the availability of each current route.
        @raise Rejected If the goal name is unknown.
        """
        revisions = self.db.rows("SELECT * FROM revisions WHERE kind='goal' AND name=%s "
                                 "ORDER BY generation DESC", (name,))
        if not revisions:
            raise Rejected("unknown_goal", name)
        # current is the newest goal revision; cache is valid only for this read snapshot.
        current, cache = revisions[0], {}
        attempts = self.db.rows("SELECT a.*, o.code,o.detail,o.manifest FROM attempts a JOIN revisions r "
                                "ON r.id=a.target LEFT JOIN outcomes o ON o.attempt=a.id "
                                "WHERE r.kind='goal' AND r.name=%s ORDER BY a.started,a.id", (name,))
        # usable collects accepted receipts whose entire dependency chain is current and intact.
        usable = []
        for att in attempts:
            att["issues"] = self._issues(att, cache)
            att["version"] = "stale" if att["issues"] else "current"
            if att["code"] in ACCEPTED and not att["issues"]:
                usable.append(att)
            att["started"] = att["started"].isoformat()
        # Each route reports one checked implication and the premise revisions still lacking complete evidence.
        routes = []
        for rule in (a for a in usable if a["code"] == "conditional"):
            missing = []
            for p in rule["request"]["premises"]:
                candidates = self.db.rows("SELECT a.id FROM attempts a JOIN outcomes o ON a.id=o.attempt "
                                          "WHERE a.target=%s AND o.code='complete'", (p,))
                if not any(not self._issues(self.db.attempt(row["id"]), cache) for row in candidates):
                    missing.append(p)
            routes.append({"rule": rule["id"], "missing": missing})
        state = "checked" if any(a["code"] == "complete" for a in usable) else "partial" if routes else "open"
        return {"goal": name, "current": current["id"], "state": state, "routes": routes,
                "issues": self._revision_issues(current["id"]), "revisions": revisions, "attempts": attempts}
