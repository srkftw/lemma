-- Generated from sim/profiles/lemmasim-virt-0.1.0.json.
-- Fixed scalar constants only; no hardware authority is conferred by this module.
namespace Lemma.Platform.LemmaSim.DeviceABI

def paperMagicOffset : UInt64 := 0
def paperVersionOffset : UInt64 := 8
def paperStatusOffset : UInt64 := 16
def paperErrorOffset : UInt64 := 24
def paperWidthOffset : UInt64 := 32
def paperHeightOffset : UInt64 := 40
def paperStrideOffset : UInt64 := 48
def paperCapsOffset : UInt64 := 56
def paperTileXOffset : UInt64 := 64
def paperTileYOffset : UInt64 := 72
def paperTileWOffset : UInt64 := 80
def paperTileHOffset : UInt64 := 88
def paperTileLenOffset : UInt64 := 96
def paperCommandOffset : UInt64 := 104
def paperSequenceOffset : UInt64 := 112
def paperRectXOffset : UInt64 := 120
def paperRectYOffset : UInt64 := 128
def paperRectWOffset : UInt64 := 136
def paperRectHOffset : UInt64 := 144
def paperModeOffset : UInt64 := 152
def paperCompletedOffset : UInt64 := 160
def paperAckOffset : UInt64 := 168
def paperResetOffset : UInt64 := 176
def paperDescriptorOffset : UInt64 := 1024
def paperApertureOffset : UInt64 := 2048
def paperBase : UInt64 := 268500992
def paperSpan : UInt64 := 4096
def paperIrq : UInt64 := 12
def paperMagic : UInt64 := 1280331856
def penMagicOffset : UInt64 := 0
def penVersionOffset : UInt64 := 8
def penStatusOffset : UInt64 := 16
def penErrorOffset : UInt64 := 24
def penCountOffset : UInt64 := 32
def penEpochOffset : UInt64 := 40
def penLossOffset : UInt64 := 48
def penMaxXOffset : UInt64 := 56
def penMaxYOffset : UInt64 := 64
def penPressureMaxOffset : UInt64 := 72
def penCapsOffset : UInt64 := 80
def penAckOffset : UInt64 := 88
def penLossAckOffset : UInt64 := 96
def penResetOffset : UInt64 := 104
def penHeadSeqOffset : UInt64 := 256
def penHeadTimeOffset : UInt64 := 264
def penHeadXOffset : UInt64 := 272
def penHeadYOffset : UInt64 := 280
def penHeadPressureOffset : UInt64 := 288
def penHeadFlagsOffset : UInt64 := 296
def penHeadToolOffset : UInt64 := 304
def penHeadButtonsOffset : UInt64 := 312
def penHeadEpochOffset : UInt64 := 320
def penBase : UInt64 := 268505088
def penSpan : UInt64 := 4096
def penIrq : UInt64 := 13
def penMagic : UInt64 := 1280331854
def descriptorMagic : UInt64 := 1280132179
def abiVersion : UInt64 := 1

end Lemma.Platform.LemmaSim.DeviceABI
