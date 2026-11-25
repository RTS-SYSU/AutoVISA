
Require Export prosa.implementation.refinements.FP.fast_search_space.
Require Export prosa.implementation.refinements.FP.refinements.
Require Export prosa.implementation.facts.job_constructor.
Require Export prosa.results.rta.ideal.fp.fully_preemptive.
Require Export prosa.implementation.refinements.FP.preemptive_sched.
From Stdlib Require Export NArith.

(** Recent versions of PROSA enable strict bullet checking, but
    the POET certificates don't yet comply with this (purely
    cosmetic) preference. So we disable the check here again. *)
#[global] Set Bullet Behavior "None".
#[global] Set Default Goal Selector "1".

Section TaskSetDeclaration.
  (** In the following, all numeric constants should be interpreted as *binary*
      numbers.  This is accomplished by opening the notation scope provided by
      the [NArith] module. *)
  Open Scope N_scope.

  Definition tsk01 :=
    [TASK id: 1
          cost: 50
          deadline: 100
          arrival: [CURVE horizon: 220 steps: [:: (1, 1); (105, 2)]]
          priority: 2].

  Definition tsk02 :=
    [PERIODIC-TASK id: 2
          cost: 10
          deadline: 100
          period: 30
          priority: 1].

  (** The above-declared tasks form the task set under analysis, which we denote
      [ts] in the following. *)
  Definition ts := [:: tsk01; tsk02].

  Lemma arrival_curve_is_valid :
    valid_taskset_arrival_curve (map taskT_to_task ts) max_arrivals.
  Proof.
    move => task IN.
    split.
    { repeat (move: IN; rewrite in_cons => /orP [/eqP -> | IN]); apply/eqP; last by done.
      all: rewrite /max_arrivals /MaxArrivals /MaxArrivals.
      all: by clear; rewrite [_ == _]refines_eq; vm_compute. }
    { repeat (move: IN; rewrite in_cons => /orP [/eqP -> | IN]); last by done.
      all: rewrite /max_arrivals /MaxArrivals /concrete_max_arrivals /task_arrival.
      have TR1 := leq_steps_is_transitive.
      all: apply extrapolated_arrival_curve_is_monotone;
        [ by apply/eqP/eqP; clear; rewrite [_ == _]refines_eq; vm_compute
        | by rewrite /sorted_leq_steps -[sorted _  _]eqb_id; clear;
          rewrite [_ == _]refines_eq; vm_compute ]. }
  Qed.

  Lemma task_set_has_valid_arrivals:
    task_set_with_valid_arrivals (map taskT_to_task ts).
  Proof.
    intros task IN.
    repeat (move: IN; rewrite in_cons => /orP [/eqP EQtsk | IN]); subst; last by done.
    all: try by clear; rewrite [_ == _]refines_eq; vm_compute.
    all: by rewrite [valid_arrivals _]refines_eq; vm_compute.
  Qed.

End TaskSetDeclaration.
