Require Import task_set.
Require tsk02.

Theorem listing_2_task_2_meets_deadline :
  forall arr_seq : arrival_sequence Job,
    arrival_sequence_uniq arr_seq ->
    all_jobs_from_taskset arr_seq (map taskT_to_task ts) ->
    consistent_arrival_times arr_seq ->
    arrivals_have_valid_job_costs arr_seq ->
    taskset_respects_max_arrivals arr_seq (map taskT_to_task ts) ->
    task_response_time_bound arr_seq (tsk02.sched arr_seq)
      (taskT_to_task task_set.tsk02) 60 /\
    60 <= task_deadline (taskT_to_task task_set.tsk02).
Proof. exact tsk02.deadline_is_respected. Qed.

Example listing_2_deadline_is_100 :
  task_deadline (taskT_to_task task_set.tsk02) = 100.
Proof. reflexivity. Qed.

Print Assumptions listing_2_task_2_meets_deadline.
Print Assumptions listing_2_deadline_is_100.
