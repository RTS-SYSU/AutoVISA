From Stdlib Require Import Arith.PeanoNat Lists.List.
From AutoRTA Require Import Model Analysis Target.
Import ListNotations.

Definition c01 := [mkTask 1 4 4; mkTask 2 5 5].
Example c01_high : check_at c01 0 = Some (Accepted 1). Proof. reflexivity. Qed.
Example c01_low : check_at c01 1 = Some (Accepted 3). Proof. reflexivity. Qed.
Example c01_nonempty_model : taskset_wf c01. Proof. repeat constructor. Qed.

Definition c02 := [mkTask 2 2 10; mkTask 1 2 10].
Example c02_guard : check_at c02 1 = Some NotAccepted. Proof. reflexivity. Qed.
Example c02_is_fixed_point :
  workload [mkTask 2 2 10] (mkTask 1 2 10) 3 = 3. Proof. reflexivity. Qed.

Example c03_equal_deadline :
  check_at [mkTask 1 1 1] 0 = Some (Accepted 1). Proof. reflexivity. Qed.
Definition one_tick : Schedule := fun t => if t =? 0 then Some 0 else None.
Example c03_endpoint : service_from one_tick 0 0 1 = 1. Proof. reflexivity. Qed.
Example c03_no_future_service : service_from one_tick 0 0 0 = 0. Proof. reflexivity. Qed.

Definition c04 := [mkTask 2 3 3; mkTask 3 10 12].
Example c04_start : initial [mkTask 2 3 3] (mkTask 3 10 12) = 5.
Proof. reflexivity. Qed.
Example c04_step1 : workload [mkTask 2 3 3] (mkTask 3 10 12) 5 = 7.
Proof. reflexivity. Qed.
Example c04_step2 : workload [mkTask 2 3 3] (mkTask 3 10 12) 7 = 9.
Proof. reflexivity. Qed.
Example c04_final : check_at c04 1 = Some (Accepted 9). Proof. reflexivity. Qed.
Example c04_budget : iterate [mkTask 2 3 3] (mkTask 3 10 12) 1 5 = Inconclusive.
Proof. reflexivity. Qed.

Example c05_equal_spacing : separated (mkTask 1 2 5) 0 5.
Proof. left. apply Nat.le_refl. Qed.
Example c05_short_spacing : ~ separated (mkTask 1 2 5) 0 4.
Proof.
  unfold separated; simpl. intros [H|H].
  - exact (Nat.nle_succ_diag_l 4 H).
  - inversion H.
Qed.

Definition idle : Schedule := fun _ => None.
Example c06_zero_job : service_from idle 0 7 (7 + 2) = 0. Proof. reflexivity. Qed.
Definition offset_tick : Schedule := fun t => if t =? 2 then Some 0 else None.
Example c07_offset_completion : service_from offset_tick 0 2 3 = 1.
Proof. reflexivity. Qed.
Example c07_before_release_excluded : service_from one_tick 0 2 3 = 0.
Proof. reflexivity. Qed.
Example c08_zero_cost_invalid : ~ task_wf (mkTask 0 1 1).
Proof. intros [H _]. inversion H. Qed.
Example c08_deadline_invalid : ~ task_wf (mkTask 1 3 2).
Proof. intros [_ [_ H]]. exact (Nat.nle_succ_diag_l 2 H). Qed.

Print Assumptions iterate_accepts_sound.

(* A nonempty, asynchronous one-job execution satisfies the complete model. *)
Definition single_arrival : Arrivals :=
  fun id => match id with 0 => Some (mkJob 0 2 1) | _ => None end.
Definition single_tasks : TaskSet := [mkTask 1 1 1].

Lemma offset_service_after : forall n,
  service_from offset_tick 0 2 (S (S (S n))) = 1.
Proof.
  induction n as [|n IH].
  - reflexivity.
  - change (service_from offset_tick 0 2 (S (S (S n))) + 0 = 1).
    rewrite Nat.add_0_r. exact IH.
Qed.

Example single_arrivals_legal : legal_arrivals single_tasks single_arrival.
Proof.
  split.
  - intros id j H. destruct id; cbn in H; try discriminate.
    inversion H; subst. exists (mkTask 1 1 1). reflexivity.
  - intros id1 id2 j1 j2 p Hneq H1 H2.
    destruct id1, id2; cbn in H1, H2; try discriminate.
    exfalso. apply Hneq. reflexivity.
Qed.

Example single_demands_bounded : bounded_demands single_tasks single_arrival.
Proof.
  intros id j p H Htask. destruct id; cbn in H; try discriminate.
  inversion H; subst. cbn in Htask. inversion Htask; subst. apply Nat.le_refl.
Qed.

Example single_schedule_valid : valid_dm_schedule single_arrival offset_tick.
Proof.
  split.
  - intros t id H. unfold offset_tick in H.
    destruct (t =? 2) eqn:E; try discriminate.
    apply Nat.eqb_eq in E. subst t.
    inversion H; subst id. exists (mkJob 0 2 1).
    split; [reflexivity|]. unfold ready. cbn. split; apply Nat.le_refl.
  - split.
    + intros t Hidle id j Ha [Hrelease Hservice].
      destruct id; cbn in Ha; try discriminate.
      inversion Ha; subst j. cbn in Hrelease.
      destruct t as [|[|[|n]]].
      * inversion Hrelease.
      * exact (Nat.nle_succ_diag_l 1 Hrelease).
      * discriminate Hidle.
      * change (service_from offset_tick 0 2 (S (S (S n))) < 1) in Hservice.
        rewrite offset_service_after in Hservice.
        exact (Nat.lt_irrefl 1 Hservice).
    + intros t id other j k Hs Hj Hk Hready.
      destruct id, other; cbn in Hj, Hk; try discriminate.
      inversion Hj; inversion Hk; subst. apply Nat.le_refl.
Qed.

Example single_taskset_valid : taskset_wf single_tasks. Proof. repeat constructor. Qed.
Example single_taskset_accepted : check_at single_tasks 0 = Some (Accepted 1).
Proof. reflexivity. Qed.
Example single_all_deadlines_met : all_deadlines_met single_tasks single_arrival offset_tick.
Proof.
  intros id j p Ha Hp. destruct id; cbn in Ha; try discriminate.
  inversion Ha; subst. cbn in Hp. inversion Hp; subst. reflexivity.
Qed.
