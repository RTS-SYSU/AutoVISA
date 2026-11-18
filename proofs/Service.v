From Stdlib Require Import Arith.PeanoNat Bool.Bool.
From AutoRTA Require Import Model.

(** Count occupied slots assigned to jobs other than the observed job.
    This definition includes equal-priority competitors; it assumes no FIFO rule.
    @param s Unit-speed schedule.
    @param id Observed job identity.
    @param release Inclusive start of the observation interval.
    @param t Exclusive end of the observation interval.
    @return Number of non-own occupied slots in [release, t). *)
Fixpoint interference_from (s : Schedule) (id release t : nat) : nat :=
  match t with
  | 0 => 0
  | S u =>
      interference_from s id release u +
      match s u with
      | Some selected =>
          if (release <=? u) && negb (id =? selected) then 1 else 0
      | None => 0
      end
  end.

(** Service never decreases when the exclusive endpoint increases.
    @param s Arbitrary schedule, including schedules not yet validated.
    @param id Observed job identity.
    @param release Fixed inclusive start.
    @param u Earlier endpoint.
    @param t Later endpoint.
    @return Monotonicity under u <= t. *)
Lemma service_monotone : forall s id release u t,
  u <= t -> service_from s id release u <= service_from s id release t.
Proof.
  (* @var Horder Endpoint ordering; IH carries the preceding monotonicity fact. *)
  intros s id release u t Horder.
  induction Horder as [|t Horder IH].
  - apply Nat.le_refl.
  - simpl. eapply Nat.le_trans; [exact IH | apply Nat.le_add_r].
Qed.

(** Both counters vanish before the interval starts.
    @param s Arbitrary schedule.
    @param id Observed job identity.
    @param release Inclusive interval start.
    @param t Endpoint at or before release.
    @return Zero own service and zero non-own service. *)
Lemma counters_before_release : forall s id release t, t <= release ->
  service_from s id release t = 0 /\ interference_from s id release t = 0.
Proof.
  (* @var Hbefore, IH Endpoint bound and zero-counter induction hypothesis. *)
  (* @var Hservice, Hinterference, Hguard Counter identities and the disabled release guard. *)
  intros s id release t. induction t as [|t IH]; intros Hbefore.
  - split; reflexivity.
  - (* @var Hprefix Counter identities for the shorter prefix. *)
    destruct (IH (Nat.le_trans _ _ _ (Nat.le_succ_diag_r t) Hbefore))
      as [Hservice Hinterference].
    assert (Hguard : (release <=? t) = false).
    { apply Nat.leb_gt. exact Hbefore. }
    simpl. rewrite Hservice, Hinterference.
    destruct (s t); [rewrite Hguard |]; split; reflexivity.
Qed.

(** Valid execution cannot give a job more service than its actual demand.
    @param a Job population.
    @param s Valid work-conserving DM schedule.
    @param id Existing job identity.
    @param j Job record returned by the arrival map.
    @param t Arbitrary endpoint, not merely the deadline.
    @return Unconditional upper bound on the job's cumulative service. *)
Lemma service_never_exceeds_demand : forall a s id j t,
  valid_dm_schedule a s -> a id = Some j ->
  service_from s id (job_release j) t <= job_demand j.
Proof.
  (* @var Hvalid, Hjob Scheduler validity and exact arrival-map membership. *)
  (* @var Hexec, Hbusy, Hpriority Execution validity, work conservation and priority discipline. *)
  (* @var IH, selected, Hselected Previous upper bound and observed dispatch identity. *)
  (* @var Htick, Hreleased, Hsame, Hlookup, Hready Executed-slot facts and the strict demand guard. *)
  intros a s id j t Hvalid Hjob.
  destruct Hvalid as [Hexec [Hbusy Hpriority]].
  induction t as [|t IH].
  - apply Nat.le_0_l.
  - simpl. destruct (s t) as [selected|] eqn:Hselected.
    + destruct ((job_release j <=? t) && (id =? selected)) eqn:Htick.
      * apply andb_true_iff in Htick. destruct Htick as [Hreleased Hsame].
        apply Nat.eqb_eq in Hsame. subst selected.
        (* @var k The executed job must be the unique record stored at id. *)
        destruct (Hexec t id Hselected) as [k [Hlookup Hready]].
        rewrite Hjob in Hlookup. inversion Hlookup; subst k.
        rewrite Nat.add_1_r. exact (proj2 Hready).
      * rewrite Nat.add_0_r. exact IH.
    + rewrite Nat.add_0_r. exact IH.
Qed.

(** A ready job forces dispatch of an existing ready job of no lower priority.
    Equal task indices remain allowed: no same-task FIFO assumption is added.
    @param a Job population.
    @param s Valid DM schedule.
    @param id Observed ready job identity.
    @param j Corresponding job record.
    @param t Dispatch slot.
    @return An executed ready job whose task index is at most job_task j. *)
Lemma pending_dispatch : forall a s id j t,
  valid_dm_schedule a s -> a id = Some j -> ready s id j t ->
  exists selected k, s t = Some selected /\ a selected = Some k /\
    ready s selected k t /\ job_task k <= job_task j.
Proof.
  (* @var Hexec, Hbusy, Hpriority Three clauses of the unchanged scheduler model. *)
  (* @var Hjob, Hready, selected, Hselected Target readiness and the observed dispatch. *)
  (* @var k, Hlookup, Hrunning Existing executed record, its membership and readiness. *)
  intros a s id j t [Hexec [Hbusy Hpriority]] Hjob Hready.
  destruct (s t) as [selected|] eqn:Hselected.
  - destruct (Hexec t selected Hselected) as [k [Hlookup Hrunning]].
    exists selected, k. split; [reflexivity|].
    split; [exact Hlookup|]. split; [exact Hrunning|].
    exact (Hpriority t selected id k j Hselected Hlookup Hjob Hready).
  - exfalso. exact (Hbusy t Hselected id j Hjob Hready).
Qed.

(** A job still pending at an interval endpoint has kept the processor busy
    throughout that interval: own service plus non-own service equals its length.
    @param a Job population.
    @param s Valid schedule.
    @param id Existing observed job.
    @param j Corresponding job record.
    @param duration Interval length measured from the job's release.
    @return Exact occupied-slot accounting, conditional on pending at the end. *)
Lemma pending_window_balance : forall a s id j duration,
  valid_dm_schedule a s -> a id = Some j ->
  service_from s id (job_release j) (job_release j + duration) < job_demand j ->
  service_from s id (job_release j) (job_release j + duration) +
    interference_from s id (job_release j) (job_release j + duration) = duration.
Proof.
  (* @var Hvalid, Hjob, IH, Hpending Scheduler facts, induction hypothesis and endpoint pendingness. *)
  (* @var Hservice, Hinterference, Hguard Base identities and enabled release guard. *)
  (* @var selected, Hselected Actual dispatched identity and its schedule equation. *)
  intros a s id j duration Hvalid Hjob.
  induction duration as [|duration IH]; intros Hpending.
  - rewrite Nat.add_0_r.
    destruct (counters_before_release s id (job_release j) (job_release j)
      (Nat.le_refl _)) as [Hservice Hinterference].
    rewrite Hservice, Hinterference. reflexivity.
  - (* @var Hprefix The target was pending at the preceding endpoint as well. *)
    assert (Hprefix : service_from s id (job_release j)
      (job_release j + duration) < job_demand j).
    { eapply Nat.le_lt_trans; [|exact Hpending].
      apply service_monotone. apply Nat.add_le_mono_l. apply Nat.le_succ_diag_r. }
    specialize (IH Hprefix).
    assert (Hguard : (job_release j <=? job_release j + duration) = true).
    { apply Nat.leb_le. apply Nat.le_add_r. }
    rewrite Nat.add_succ_r. simpl.
    destruct (s (job_release j + duration)) as [selected|] eqn:Hselected.
    + rewrite Hguard. simpl.
      destruct (id =? selected); simpl;
        rewrite Nat.add_0_r, Nat.add_1_r.
      * rewrite Nat.add_succ_l, IH. reflexivity.
      * rewrite Nat.add_succ_r, IH. reflexivity.
    + (* An idle slot contradicts work conservation while the target is ready. *)
      exfalso. apply (proj1 (proj2 Hvalid) _ Hselected id j Hjob).
      split; [apply Nat.le_add_r | exact Hprefix].
Qed.

(** A concrete capacity witness is sufficient for the lower service bound.
    No arrival-count or analytical workload bound is assumed by this lemma.
    @param a Job population.
    @param s Valid schedule.
    @param id Existing observed job.
    @param j Corresponding job record.
    @param deadline Relative deadline bound.
    @return Completion by the deadline if some interval has sufficient capacity. *)
Lemma capacity_implies_service_lower : forall a s id j deadline,
  valid_dm_schedule a s -> a id = Some j ->
  (exists duration, duration <= deadline /\
    interference_from s id (job_release j) (job_release j + duration) +
      job_demand j <= duration) ->
  job_demand j <= service_from s id (job_release j) (job_release j + deadline).
Proof.
  (* @var Hvalid, Hjob Scheduler validity and target membership. *)
  (* @var duration, Hwithin, Hcapacity Concrete capacity witness and its two bounds. *)
  (* @var Hdone, Hpending, Hprefix Completion cases and the earlier pending endpoint. *)
  (* @var Htoo_many Strict capacity contradiction after exact interval accounting. *)
  intros a s id j deadline Hvalid Hjob [duration [Hwithin Hcapacity]].
  destruct (Nat.le_gt_cases (job_demand j)
    (service_from s id (job_release j) (job_release j + deadline))) as [Hdone|Hpending].
  - exact Hdone.
  - exfalso.
    assert (Hprefix : service_from s id (job_release j)
      (job_release j + duration) < job_demand j).
    { eapply Nat.le_lt_trans; [|exact Hpending].
      apply service_monotone. apply Nat.add_le_mono_l. exact Hwithin. }
    (* @var Hbalance Exact busy-slot identity makes the capacity contradiction arithmetic. *)
    pose proof (pending_window_balance a s id j duration Hvalid Hjob Hprefix) as Hbalance.
    assert (Htoo_many : duration <
      interference_from s id (job_release j) (job_release j + duration) + job_demand j).
    { rewrite <- Hbalance at 1. rewrite Nat.add_comm.
      apply Nat.add_lt_mono_l. exact Hprefix. }
    exact (Nat.lt_irrefl duration (Nat.lt_le_trans _ _ _ Htoo_many Hcapacity)).
Qed.
