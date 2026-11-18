From Stdlib Require Import Arith.PeanoNat.
Definition smoke_target : Prop := forall n : nat, n + 0 = n.
