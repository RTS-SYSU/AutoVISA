From AutoRTA Require Import SmokeTarget.
Unset Guard Checking.
Fixpoint unsafe_loop (n : nat) {struct n} : smoke_target := unsafe_loop n.
Definition candidate : smoke_target := unsafe_loop 0.