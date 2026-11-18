"""Construct typed case_11 definitions and explicit universal target quantification."""


def var(name):
    """Create a bound variable reference.

    @param name Variable identifier.
    @return Variable expression.
    """
    return {"op":"var","name":name}


def call(symbol, *args):
    """Construct a typed function application for subsequent validation.

    @param symbol Approved function identity.
    @param args Ordered argument expressions.
    @return Application expression.
    """
    return {"op":"call","symbol":symbol,"args":list(args)}


def binary(op, left, right):
    """Create a binary expression without rendering source text.

    @param op Arithmetic, comparison or implication constructor.
    @param left Left operand.
    @param right Right operand.
    @return Binary expression.
    """
    return {"op":op,"left":left,"right":right}


def quantify(parameters, body):
    """Bind variables in their declared outer-to-inner order.

    @param parameters Ordered name/sort pairs.
    @param body Proposition under those binders.
    @return Nested universal quantification.
    """
    # @var name, sort Binder identity and type; reverse traversal preserves declared scope order.
    for name, sort in reversed(parameters):
        body = {"op":"forall","name":name,"sort":sort,"body":body}
    return body


def definitions():
    """Build the algorithm arithmetic and finite-accepting-trace predicate.

    @return Ordered typed definitions, each linked to semantic item keys.
    """
    # Short mathematical names refer to typed variables; no user strings become Rocq code.
    hp, p, q, t, period, ts, i = map(var, ("hp","p","q","t","period","ts","i"))
    # @var cost, deadline Own-task bounds; qcost and qperiod describe one higher-priority task.
    cost, deadline, qcost, qperiod = call("cost",p), call("deadline",p), call("cost",q), call("period",q)
    # @var ceiling Ceiling division on natural ticks; task well-formedness ensures positive periods.
    ceiling = binary("div", binary("sub", binary("add",t,period), {"op":"nat","value":1}), period)
    # @var initial Fig.3 starts at the sum of own and higher-priority execution bounds.
    initial = {"op":"sum","name":"q","over":hp,"seed":cost,"body":qcost}
    # @var workload Interference demand at the current iteration point.
    workload = {**initial,"body":binary("mul",call("ir_ceil_div",t,qperiod),qcost)}
    # @var floor_count Number of full higher-priority periods before the own-task deadline.
    floor_count = binary("div",deadline,qperiod)
    # @var truncated Test 2 demand including the bounded final partial period.
    truncated = binary("add",binary("mul",floor_count,qcost),
                       binary("min",qcost,binary("sub",deadline,binary("mul",floor_count,qperiod))))
    # Acceptance is a finite trace using W01's locked inductive relation, including its deadline guards.
    acceptance = quantify([["i","Nat"],["p","Task"]], binary("implies",
                 binary("eq",call("lookup",ts,i),call("some_task",p)),
                 call("accepts_from",call("prefix",i,ts),p,call("ir_initial",call("prefix",i,ts),p))))
    return [
        {"name":"ir_ceil_div","parameters":[["t","Nat"],["period","Nat"]],"result":"Nat","body":ceiling,"sources":["fig3"]},
        {"name":"ir_initial","parameters":[["hp","TaskSet"],["p","Task"]],"result":"Nat","body":initial,"sources":["fig3"]},
        {"name":"ir_workload","parameters":[["hp","TaskSet"],["p","Task"],["t","Nat"]],"result":"Nat","body":workload,"sources":["fig3"]},
        {"name":"ir_test1","parameters":[["hp","TaskSet"],["p","Task"]],"result":"Prop",
         "body":binary("le",call("ir_workload",hp,p,deadline),deadline),"sources":["test1"]},
        {"name":"ir_test2","parameters":[["hp","TaskSet"],["p","Task"]],"result":"Prop",
         "body":binary("le",{**initial,"body":truncated},deadline),"sources":["test2"]},
        {"name":"ir_fig3_accepts","parameters":[["ts","TaskSet"]],"result":"Prop","body":acceptance,"sources":["fig3"]},
    ]


def proposition():
    """Reconstruct the main goal without using its existing theorem alias.

    @return Universally quantified implication with all five required premises.
    """
    # @var ts, a, s Arbitrary task set, arrival population and candidate schedule.
    ts, a, s = map(var, ("ts","a","s"))
    # @var premises All required obligations in the exact W01 implication order.
    premises = [call("taskset_wf",ts), call("legal_arrivals",ts,a), call("bounded_demands",ts,a),
                call("valid_dm_schedule",a,s), call("ir_fig3_accepts",ts)]
    # @var body Required deadline guarantee, progressively wrapped in every premise.
    body = call("deadlines_met",ts,a,s)
    for premise in reversed(premises):
        body = binary("implies",premise,body)
    return quantify([["ts","TaskSet"],["a","Arrivals"],["s","Schedule"]],body)


#: Explicit semantic-to-kernel bindings; exact source bytes are pinned by the mapping profile.
MODEL_BINDINGS = {
    "taskset_wf": {"file":"Model.v","symbol":"taskset_wf","items":["parameter_order","dm_priority"],"choices":["positive_parameters","scheduler"]},
    "legal_arrivals": {"file":"Model.v","symbol":"legal_arrivals","items":["sporadic_separation","sporadic_deadline","mixed_tasks"],"choices":["sporadic_traces","integer_time"]},
    "bounded_demands": {"file":"Model.v","symbol":"bounded_demands","items":["parameter_order"],"choices":["sporadic_traces","positive_parameters"]},
    "valid_dm_schedule": {"file":"Model.v","symbol":"valid_dm_schedule","items":["dm_priority"],"choices":["scheduler","execution_scope"]},
    "deadlines_met": {"file":"Model.v","symbol":"all_deadlines_met","items":["fig3_acceptance_soundness"],"choices":["integer_time","sporadic_traces"]},
    "accepts_from": {"file":"Analysis.v","symbol":"accepts_from","items":["fig3"],"choices":["integer_time","positive_parameters"]},
}
