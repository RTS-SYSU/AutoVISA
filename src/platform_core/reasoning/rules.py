"""Executable local proof rules, constructed independently of the paper's proof."""

from platform_core.evidence.terms import Rejected

#: Reviewed proof constructors; actual success is decided by Rocq for each exact requested type.
PROOFS = {
    # General lemmas are authored locally; every use still undergoes the normal exact-type audit.
    "service_monotone":"AutoRTA.Service.service_monotone",
    "counters_before_release":"AutoRTA.Service.counters_before_release",
    "service_never_exceeds_demand":"AutoRTA.Service.service_never_exceeds_demand",
    "pending_dispatch":"AutoRTA.Service.pending_dispatch",
    "pending_window_balance":"AutoRTA.Service.pending_window_balance",
    "capacity_implies_service_lower":"AutoRTA.Service.capacity_implies_service_lower",
    # @var Hupper Checked general service bound, specialized without using workload assumptions.
    "service_upper_from_execution":"""ltac:(intros Hupper ts a s Hwf Ha Hd Hs Hw jid j p Hj Hp;
        exact (Hupper a s jid j (job_release j + task_deadline p) Hs Hj))""",
    # @var Hcapacity Unproved analysis-to-capacity premise; Hbridge is the checked local scheduling lemma.
    "service_lower_from_capacity":"""ltac:(intros Hcapacity Hbridge ts a s Hwf Ha Hd Hs Hw jid j p Hj Hp;
        exact (Hbridge a s jid j (task_deadline p) Hs Hj
          (Hcapacity ts a s Hwf Ha Hd Hs Hw jid j p Hj Hp)))""",
    "trace_witness":"""ltac:(intros hp p t H; induction H as [t HD HW | t HD HG Hnext IH];
        [exists t; split; assumption | exact IH])""",
    "trace_guard":"ltac:(intros hp p t H; destruct H; assumption)",
    "cost_lower_bound":"""ltac:(intros hp p t; unfold workload; induction hp as [|q hp IH]; simpl;
        [apply Nat.le_refl | eapply Nat.le_trans; [exact IH | apply Nat.le_add_l]])""",
    "instantiate_witness":"""ltac:(intros Htrace ts Haccept i p Hlookup;
        apply (Htrace (firstn i ts) p (initial (firstn i ts) p));
        exact (Haccept i p Hlookup))""",
    "root_via_witness":"""ltac:(intros Hw Hb ts a s Hwf Ha Hd Hs Haccept;
        apply (Hb ts a s Hwf Ha Hd Hs); exact (Hw ts Haccept))""",
    "bridge_from_service_bounds":"""ltac:(intros Hlower Hupper ts a s Hwf Ha Hd Hs Hw;
        unfold all_deadlines_met; intros jid j p Hj Hp;
        apply Nat.le_antisymm;
        [exact (Hupper ts a s Hwf Ha Hd Hs Hw jid j p Hj Hp)
        |exact (Hlower ts a s Hwf Ha Hd Hs Hw jid j p Hj Hp)])""",
    "root_via_jobs":"""ltac:(intros H ts a s Hwf Ha Hd Hs Haccept;
        unfold all_deadlines_met; intros jid j p Hj Hp;
        exact (H ts a s Hwf Ha Hd Hs Haccept (job_task j) p jid j Hp Hj eq_refl))""",
}


def proof(name):
    """Resolve one locally implemented rule into a proof term.

    @param name Stable rule key, never arbitrary user-provided Rocq syntax.
    @return Candidate proof expression to send through the ordinary evidence checks.
    @raise Rejected If no reviewed implementation exists for this rule.
    """
    if not isinstance(name,str) or name not in PROOFS:
        raise Rejected("unknown_rule",str(name))
    from .statements import claims, implies, render
    # @var statements Independent declared types guide Ltac before the target wrapper checks conversion.
    statements = claims()
    required = {"service_upper_from_execution":(["service_never_exceeds_demand"],"service_upper"),
                "service_lower_from_capacity":(["capacity_witnesses","capacity_implies_service_lower"],"service_lower"),
                "bridge_from_service_bounds":(["service_lower","service_upper"],"response_bridge"),
                "instantiate_witness":(["trace_witness"],"task_witnesses"),
                "root_via_witness":(["task_witnesses","response_bridge"],"root"),
                "root_via_jobs":(["direct_jobs"],"root")}
    premises,target = required.get(name,([],name))
    typ = render(implies([statements[key] for key in premises],statements[target]))
    return "(" + PROOFS[name] + " : " + typ + ")"
