(** Concrete endpoint checks complement the universally quantified scheduling proofs.
    @param t Integer dispatch slot.
    @return Alternating job identities after an initially idle prefix. *)
Definition alternating (t : nat) : option nat :=
  match t with 2 => Some 0 | 3 => Some 1 | 4 => Some 0 | _ => None end.

(** The release endpoint itself excludes its dispatch slot. *)
Example release_endpoint : service_from alternating 0 2 2 = 0.
Proof. reflexivity. Qed.
(** The first executed slot appears at its successor endpoint. *)
Example first_slot : service_from alternating 0 2 3 = 1.
Proof. reflexivity. Qed.
(** A competing identity contributes no own service. *)
Example competing_slot : service_from alternating 0 2 4 = 1.
Proof. reflexivity. Qed.
(** The competing slot belongs to the non-own counter, irrespective of task priority. *)
Example competing_count : interference_from alternating 0 2 4 = 1.
Proof. reflexivity. Qed.
(** Half-open endpoint accounting includes the final slot only after it finishes. *)
Example final_slot : service_from alternating 0 2 5 = 2.
Proof. reflexivity. Qed.
(** Starting a window later removes earlier service. *)
Example later_release : service_from alternating 0 4 5 = 1.
Proof. reflexivity. Qed.
(** Idle slots are not counted as non-own execution. *)
Example idle_is_not_interference : interference_from alternating 0 5 8 = 0.
Proof. reflexivity. Qed.
(** Zero-length windows have zero counters. *)
Example empty_interval : interference_from alternating 0 4 4 = 0.
Proof. reflexivity. Qed.
(** Equal task indices still permit distinct competing job identities. *)
Example distinct_same_task :
  job_task (mkJob 0 2 1) = job_task (mkJob 0 3 1) /\
  interference_from alternating 0 2 4 = 1.
Proof. split; reflexivity. Qed.
(** Zero-demand jobs cannot be ready at release. *)
Example zero_demand_not_ready : ~ ready alternating 0 (mkJob 0 2 0) 2.
Proof. intros [_ H]. exact (Nat.nlt_0_r _ H). Qed.
(** Already-completed jobs cannot be ready for another dispatch. *)
Example completed_not_ready : ~ ready alternating 0 (mkJob 0 2 1) 3.
Proof. intros [_ H]. exact (Nat.lt_irrefl _ H). Qed.
(** Idle schedules violate no-idle accounting only when no readiness premise is supplied:
    the unconditional occupancy equality is deliberately false. *)
Example idle_not_full : service_from (fun _ => None) 0 0 2 +
  interference_from (fun _ => None) 0 0 2 <> 2.
Proof. discriminate. Qed.
Definition candidate : True := I.
