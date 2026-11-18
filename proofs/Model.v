From Stdlib Require Import Arith.PeanoNat Lists.List Bool.Bool.
Import ListNotations.

Record Task := mkTask { task_cost : nat; task_deadline : nat; task_period : nat }.
Definition TaskSet := list Task.
Definition task_wf (p : Task) : Prop :=
  0 < task_cost p /\ task_cost p <= task_deadline p /\
  task_deadline p <= task_period p.

Fixpoint dm_ordered (ts : TaskSet) : Prop :=
  match ts with
  | [] => True
  | p :: rest =>
      Forall (fun q => task_deadline p <= task_deadline q) rest /\ dm_ordered rest
  end.
(* Position in this fixed DM-ordered list is the stable tie-break and identity. *)
Definition taskset_wf (ts : TaskSet) : Prop := Forall task_wf ts /\ dm_ordered ts.

Record Job := mkJob { job_task : nat; job_release : nat; job_demand : nat }.
(* Arbitrary finite or infinite job populations, indexed by unique natural IDs. *)
Definition Arrivals := nat -> option Job.
Definition Schedule := nat -> option nat.
Definition separated (p : Task) (r s : nat) : Prop :=
  r + task_period p <= s \/ s + task_period p <= r.

Definition legal_arrivals (ts : TaskSet) (a : Arrivals) : Prop :=
  (forall id j, a id = Some j -> exists p, nth_error ts (job_task j) = Some p) /\
  (forall id1 id2 j1 j2 p,
    id1 <> id2 -> a id1 = Some j1 -> a id2 = Some j2 ->
    job_task j1 = job_task j2 -> nth_error ts (job_task j1) = Some p ->
    separated p (job_release j1) (job_release j2)).

Definition bounded_demands (ts : TaskSet) (a : Arrivals) : Prop :=
  forall id j p, a id = Some j -> nth_error ts (job_task j) = Some p ->
    job_demand j <= task_cost p.

(* Execution at u supplies service over [u,u+1); before-release service is excluded. *)
Fixpoint service_from (s : Schedule) (id release t : nat) : nat :=
  match t with
  | 0 => 0
  | S u =>
      service_from s id release u +
      match s u with
      | Some selected => if (release <=? u) && (id =? selected) then 1 else 0
      | None => 0
      end
  end.
Definition ready (s : Schedule) (id : nat) (j : Job) (t : nat) : Prop :=
  job_release j <= t /\ service_from s id (job_release j) t < job_demand j.

Definition valid_dm_schedule (a : Arrivals) (s : Schedule) : Prop :=
  (forall t id, s t = Some id -> exists j, a id = Some j /\ ready s id j t) /\
  (forall t, s t = None -> forall id j, a id = Some j -> ~ ready s id j t) /\
  (forall t id other j k,
    s t = Some id -> a id = Some j -> a other = Some k ->
    ready s other k t -> job_task j <= job_task k).

Definition all_deadlines_met (ts : TaskSet) (a : Arrivals) (s : Schedule) : Prop :=
  forall id j p, a id = Some j -> nth_error ts (job_task j) = Some p ->
    service_from s id (job_release j) (job_release j + task_deadline p) = job_demand j.
