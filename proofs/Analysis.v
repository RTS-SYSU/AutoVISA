From Stdlib Require Import Arith.PeanoNat Lists.List.
From AutoRTA Require Import Model.
Import ListNotations.

Definition ceil_div (t period : nat) : nat := (t + period - 1) / period.
Definition initial (hp : TaskSet) (p : Task) : nat :=
  fold_right (fun q acc => task_cost q + acc) (task_cost p) hp.
Definition workload (hp : TaskSet) (p : Task) (t : nat) : nat :=
  fold_right (fun q acc => ceil_div t (task_period q) * task_cost q + acc)
    (task_cost p) hp.

Inductive IterationResult :=
| Accepted (witness : nat)
| NotAccepted
| Inconclusive.

(* Exhaustion is distinct from mathematical rejection; no unproved totality assumption. *)
Fixpoint iterate (hp : TaskSet) (p : Task) (fuel t : nat) : IterationResult :=
  match fuel with
  | 0 => Inconclusive
  | S remaining =>
      if task_deadline p <? t then NotAccepted else
      let q := workload hp p t in
      if q <=? t then Accepted t else iterate hp p remaining q
  end.
Definition check_task (hp : TaskSet) (p : Task) : IterationResult :=
  iterate hp p (S (task_deadline p)) (initial hp p).
Definition check_at (ts : TaskSet) (i : nat) : option IterationResult :=
  match nth_error ts i with
  | None => None
  | Some p => Some (check_task (firstn i ts) p)
  end.

(* Finite accepting traces: no floating arithmetic, no fixed-point-only shortcut. *)
Inductive accepts_from (hp : TaskSet) (p : Task) : nat -> Prop :=
| accept_here : forall t,
    t <= task_deadline p -> workload hp p t <= t -> accepts_from hp p t
| accept_later : forall t,
    t <= task_deadline p -> t < workload hp p t ->
    accepts_from hp p (workload hp p t) -> accepts_from hp p t.

Definition fig3_accepts (ts : TaskSet) : Prop :=
  forall i p, nth_error ts i = Some p ->
    accepts_from (firstn i ts) p (initial (firstn i ts) p).

Lemma iterate_accepts_sound : forall fuel hp p t witness,
  iterate hp p fuel t = Accepted witness -> accepts_from hp p t.
Proof.
  induction fuel as [|fuel IH]; intros hp p t witness H; simpl in H.
  - discriminate.
  - destruct (task_deadline p <? t) eqn:Hd; try discriminate.
    apply Nat.ltb_ge in Hd.
    destruct (workload hp p t <=? t) eqn:Hq.
    + apply Nat.leb_le in Hq. apply accept_here; assumption.
    + apply Nat.leb_gt in Hq. eapply accept_later; eauto.
Qed.
