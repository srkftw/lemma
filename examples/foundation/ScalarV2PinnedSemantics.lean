/-!
Direct probes of the pinned host Lean implementation for the edge semantics that
`core0-v0.2` must preserve.  This file intentionally imports no custom compiler or
checked-model module.
-/

private def emit (name : String) (value : Nat) : IO Unit :=
  IO.println s!"PINNED_UINT:{name}:{value}"

def scalarV2PinnedSemanticsProbe : IO Unit := do
  emit "u8-div-zero" (((255 : UInt8) / 0).toNat)
  emit "u8-rem-zero" (((255 : UInt8) % 0).toNat)
  emit "u8-shl-width" (((1 : UInt8) <<< (8 : UInt8)).toNat)
  emit "u8-shl-width-plus-one" (((1 : UInt8) <<< (9 : UInt8)).toNat)
  emit "u8-shr-max-count" (((255 : UInt8) >>> (255 : UInt8)).toNat)
  emit "u8-complement" ((~~~(0 : UInt8)).toNat)
  emit "u32-div-zero" (((0xffffffff : UInt32) / 0).toNat)
  emit "u32-rem-zero" (((0xffffffff : UInt32) % 0).toNat)
  emit "u32-shl-width" (((1 : UInt32) <<< (32 : UInt32)).toNat)
  emit "u32-shl-width-plus-one" (((1 : UInt32) <<< (33 : UInt32)).toNat)
  emit "u32-shr-max-count" (((0xffffffff : UInt32) >>> (0xffffffff : UInt32)).toNat)
  emit "u32-complement" ((~~~(0 : UInt32)).toNat)
  emit "u64-div-zero" (((0xffffffffffffffff : UInt64) / 0).toNat)
  emit "u64-rem-zero" (((0xffffffffffffffff : UInt64) % 0).toNat)
  emit "u64-shl-width" (((1 : UInt64) <<< (64 : UInt64)).toNat)
  emit "u64-shl-width-plus-one" (((1 : UInt64) <<< (65 : UInt64)).toNat)
  emit "u64-shr-max-count"
    (((0xffffffffffffffff : UInt64) >>> (0xffffffffffffffff : UInt64)).toNat)
  emit "u64-complement" ((~~~(0 : UInt64)).toNat)

#eval scalarV2PinnedSemanticsProbe
