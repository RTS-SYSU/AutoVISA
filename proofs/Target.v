From AutoRTA Require Import Model Analysis.

(* This is a proposition DEFINITION, not a theorem, axiom, or admitted proof. *)
Definition case11_fig3_acceptance_soundness_int_v1 : Prop :=
  forall (ts : TaskSet) (a : Arrivals) (s : Schedule),
    taskset_wf ts ->
    legal_arrivals ts a ->
    bounded_demands ts a ->
    valid_dm_schedule a s ->
    fig3_accepts ts ->
    all_deadlines_met ts a s.

Check case11_fig3_acceptance_soundness_int_v1 : Prop.
