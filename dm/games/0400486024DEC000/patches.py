# The Legend of Zelda: Ocarina of Time (0400486024DEC000): the rewriter's patches of this game's own code. dm/tools/patch_nso.py loads every profile's patches.py;
# MATCH_FRAME_STEP as described there ("Registered patches"). Patches of Nintendo SDK module builds are in dm/tools/sdk_patches.py
from nso_asm import ADRP, B

# The game's frame ratio. Once a frame the function at main+0x6e6be0 (v131072) divides its base rate (60.0, or 30.0 while bit 0 of [x21+0x24f] is set) by the int frame rate at
# [x21+0x2c8] (fdiv s8,s1,s0 at +0xe4) and hands the result to the time object (main+0x3b4e300: ratio at +0x10, 1 / ratio at +0x14, round(60 / ratio) at +0x1c), which the game
# steps by; the frame's own time never enters it, so a frame that takes two vsyncs at rate 60 plays at half speed. The stub gives the ratio the host's step instead: step × base / 60
# (the division's value when the host keeps frames 60 / rate vsyncs), and counts the vsyncs stepped. Until the host has decided a step, and at fps_target 0, the division runs.
# s0 and x16 / x17 are free there (s0 is written again on every path before it is read; the function uses neither x16 nor x17); s1 keeps the base rate.
# Lichii (a GPL emulator; only the fact was taken) found the division (its notes: main+0x6E6CC4, 60 / [x21+0x2C8])
def frame_step(ctx):
    here, emit, fs_site, fs_put, FS_STATE_OFF, base = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state, ctx.base
    site = base + 0xe4
    fs_site(site, '2818201e')   # fdiv s8,s1,s0
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9400211,   # ldr w17,[x16]          target fps (0 = off)
              0x340001b1,   # cbz w17,orig (+13)
              0xb9402211,   # ldr w17,[x16,#0x20]    step in vsyncs
              0x34000171,   # cbz w17,orig (+11)     not decided yet
              0x1e230220,   # ucvtf s0,w17
              0xf9401a10,   # ldr x16,[x16,#0x30]
              0x8b110210):  # add x16,x16,x17
        emit(w)
    emit(ADRP(17, here(), FS_STATE_OFF))
    for w in (0xf9001a30,   # str x16,[x17,#0x30]    vsyncs stepped
              0x1e210808,   # fmul s8,s0,s1          step × base rate
              0x52a84e10,   # mov w16,#0x42700000    60.0
              0x1e270200,   # fmov s0,w16
              0x1e201908):  # fdiv s8,s8,s0          / 60
        emit(w)
    emit(B(here(), site + 4))
    emit(0x1e201828); emit(B(here(), site + 4))   # orig: fdiv s8,s1,s0; back
    fs_put(site, [B(site, start)], 'frame ratio: the host\'s step × base rate / 60 instead of base rate / the game\'s frame rate (state page target fps; 0 = the game\'s ratio)')
    dynamic_resolution(ctx)
    window_size(ctx)

# The game's dynamic resolution (game__gfx__DynamicResolutionParam: LoadThreshold, ReduceCounterMax, IncreaseCounterMax and a list of levels, each a ResolutionReduceScale and a
# Priority; on v131072 levels 0..9 at 0.75..0.333 of 2048x1152, 1536x864 to 683x384). Its update (main+0x805aa0) reads the frame's GPU load (about 0.2 ms a unit) into +0x8, subtracts
# its small model of the fixed costs and divides the rest by the square of the current scale: it takes the rest of the frame's cost to grow with the pixel count, as on the Switch 2
# its constants were tuned for. The level function (main+0x8065e0) adds that back times each level's scale squared and returns the best level under the threshold (+0x10, 83 = about
# 16.4 ms). On Apple GPUs this game's cost hardly depends on the resolution (mesh, compute and the upscaler's fixed 2048x1152 dominate): 683x384 cost 14.3 ms and 1536x864 14.7 ms on
# an M4 Pro, yet at 683x384 the extrapolation put 1536x864 at about 300 units against the 83 it allows, so the controller sat at its floor for good (game note, Dynamic resolution).
# The stub replaces the level function. With DM_DYNAMIC_RESOLUTION 0 (the default; state +0x40 0) it returns 0: full resolution. With 1 it climbs on what was measured at each
# level, with no model of how the cost grows: one level down when the load (+0x8) has been over the threshold for 8 calls in a row, and that level is marked as not fitting; one level
# up when the load fits and the level above was never measured, fitted when it was last measured, or was measured more than 600 calls (about 10 s) ago; else the current level
# (+0x174). Nothing is decided or recorded until a level has held 8 calls: the load is read a few frames late, so before that it may be the previous level's. The 8 calls over in a
# row keep a single slow frame, or the first frames at a new size (its render targets), from marking a level that fits (on the full library at level 1: one burst to 90 against loads
# of 77-80 at levels 2 and 1). The game's counters still pace the steps (down after ReduceCounterMax frames, up after IncreaseCounterMax); its level count (+0x1a0) is the floor.
# The memory is in the state page: +0x200 calls, +0x204 the last call's level, +0x208 calls at it, +0x20c calls over in a row, +0x210 the load measured at each level (16 floats),
# +0x250 the call it was measured at (0 = never). Run against a model of the update (a level moves after the stub asked 5 times up or 2 times down; the load two frames late): a load
# of 70 at every level climbs from the floor to full size in 9 steps, as does Ocarina's measured 72-80 with a spike every 37 frames and a burst after each change; a load that grows
# with the pixel count settles at the highest level that fits and tries the one above once per 600 calls; a scene that gets lighter climbs again, a heavier one steps down.
# The function is a leaf: x2..x11, x16, x17 and s0..s2 are free, w0 its only result (the original also stores its predicted cost at +0x18, which only it and the update's own
# decision read). The update's fingerprint is required too: +0x8 and +0x174 are its fields
drs_controller = (   # drs_stub.s, assembled with clang; x0 the controller, x16 the state page (the ADRP before it)
    0xb9404211, 0x35000071, 0x2a1f03e0, 0xd65f03c0,                                                   # off (state +0x40 0): level 0
    0xbd400800, 0xbd401001, 0xb9417402, 0xb941a003, 0x7100005f, 0x1a9fa042, 0x528001e9, 0x6b09005f,   # load, threshold, level (0..15), count
    0x1a89d042, 0xb9420204, 0x11000484, 0xb9020204, 0xb9420605, 0xb9420a06, 0x6b0200bf, 0x1a8617e6,   # calls + 1; calls at this level
    0xb9020602, 0xb9020a06, 0x35000046, 0xb9020e1f, 0x91084207, 0x91094208, 0x710020df, 0x5400040b,   # a new level: none over; under 8 calls: stay
    0x1e212000, 0x540001ad, 0xb9420e0b, 0x1100056b, 0xb9020e0b, 0x7100217f, 0x5400032b,               # over: under 8 in a row, stay
    0xbc2258e0, 0xb8225904, 0x51000469, 0x1100044a, 0x6b09015f, 0x1a89d140, 0xd65f03c0,               # 8 in a row: record it, down one (to the floor)
    0xb9020e1f, 0xbc2258e0, 0xb8225904, 0x34000182, 0x51000449, 0xb869590a, 0x340000ea, 0x4b0a008a,   # fits: record it; at 0 stay; the level above's record
    0x7109615f, 0x54000088, 0xbc6958e2, 0x1e212040, 0x540000aa, 0x2a0903e0, 0xd65f03c0,               # never, stale or fitting: up one
    0x2a1f03e0, 0xd65f03c0, 0x2a0203e0, 0xd65f03c0)                                                   # 0; or stay
def dynamic_resolution(ctx):
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    site = ctx.others.get('dynamic resolution')
    if site is None or ctx.others.get('dynamic resolution update') is None: return   # not both found in this build (a red line from the locator): the game's own dynamic resolution
    fs_site(site, '017c40bd')   # ldr s1,[x0,#0x7c]
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in drs_controller: emit(w)
    fs_put(site, [B(site, start)], 'dynamic resolution level: 0 (full resolution), or with state +0x40 (DM_DYNAMIC_RESOLUTION) a climb on the load measured at each level')
    ctx.capabilities.add('DYNAMIC_RESOLUTION')

# The boot window's size (static reading by another session, ~/Documents/ultra-mod/oot-4k-window.md, the facts below rechecked on v131072's main). nnMain (main+0x1202ce0, 0x570
# bytes) builds the framework's CreateArg on its stack and fixes the window at 2560x1440 at +0x200: mov x8,#0xa00; movk x8,#0x5a0,lsl#32; stur x8,[x21,#0x14] (x21 = sp+0xc8). The
# framework keeps the pair (fw+0x9c / +0xa0), its graphics init (main+0x346be50) turns it into the display buffer's floats, and main+0x527fc0 makes the swap chain of that size
# ("WindowInitialize ... 2560x1440"), before any game file but HeapDef and the boot config is read. The size is not asked of the host (no display query, tier or mode), and the
# same constant serves handheld. The game's own runtime limit already allows 4K docked: main+0x112c5e0 takes {640x480, ..., 2560x1440, 3840x2160}[6 - graphics tier] (main+0x3f58540),
# so with a 3840x2160 window the scene follows its ResolutionParam (Bootup's ModelSceneExtensionParam) up to it. The stub gives the window the host's size: state +0x2c0, a u64
# width | height << 32 the loader writes from DM_DISPLAY_BUFFER (2160, 1440, 1080) when docked and the build declares WINDOW_SIZE; 0 = the game's 2560x1440. It replaces the mov
# (a branch to it) and the movk (a nop), and goes back to the stur. nnMain uses neither x16 nor x17, nothing branches to +0x204 or +0x208, and neither word is a rewrite site.
# The window textures grow with it (3840x2160 RGBA8 x2 about 64 MB, from the root before HeapDef's heaps exist); the scene's own targets come out of HeapDef's
# DynamicTextureAllocatorMem, which a 4K scene needs grown (the oot-4k overlay, with DM_HEAP_EXTRA)
# The window alone leaves the 3D scene and its crop at 2560x1440 (ygy-75's canary: "boot window 3840x2160", WindowInitialize 3840x2160, WindowCrop and the scene passes still
# 2560x1440). They come from a size pair at +8 of the graphics init's argument: the init (main+0x1087b70, 0x2fc bytes, one caller, bl at main+0x36aef98 with x1 = sysobj+0x708)
# passes arg+8 to main+0x1087f40, which compares it with gfx+0x10 (crop and base) and copies it there as a u64 (ldp w8,w9,[x1]; ldr x8,[x1]; str x8,[x0,#0x10]), and to the
# copy of the first level table at main+0x1087e70 (ldr x12,[x1] into gfx+0xf4). The runtime update's min() with the window limit (main+0x6502e0) does not run at boot.
# WORKAROUND at the value's consumer: the second stub, at the init's entry, stores the same host word over arg+8 before the init reads it (0 leaves the game's value). Open: who
# writes 2560x1440 there (before the init, about 0.108 s into the boot; not file data, and no constant found statically for it); a fix there would replace this stub. Another
# reader of arg+8 before the init would keep 2560x1440 (a mismatch in the canary). The relocated pacibsp signs LR with SP as before: the branch to the stub and the stub write
# neither, so the autibsp before the init's tail call (+0x2b0) checks the same signature. The init uses neither x16 nor x17, nothing branches to its +4, and its entry is no
# rewrite site (checked on v131072's main, 2026-11-16)
def window_size(ctx):
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    init = ctx.others.get('gfx init')
    if init is not None:
        fs_site(init, '7f2303d5')   # pacibsp
        start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
        for w in (0xf9416211,   # ldr x17,[x16,#0x2c0]   the host's size (w | h << 32), 0 = the game's
                  0xb4000051,   # cbz x17,+8             unset: leave arg+8 alone
                  0xf9000431,   # str x17,[x1,#8]        arg+8: the 3D base and crop the init takes
                  0xd503237f):  # pacibsp                the instruction replaced
            emit(w)
        emit(B(here(), init + 4))
        fs_put(init, [B(init, start)], 'graphics init: the 3D base and crop at arg+8 from the host (state +0x2c0, DM_DISPLAY_BUFFER docked; workaround at the consumer, the writer is open)')
        ctx.capabilities.add('WINDOW_SIZE')
    fn = ctx.others.get('window size')
    if fn is None: return   # not found in this build (a red line from the locator): the game's 2560x1440
    site = fn + 0x200
    fs_site(site, '084081d208b4c0f2')   # mov x8,#0xa00; movk x8,#0x5a0,lsl#32
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xf9416208,   # ldr x8,[x16,#0x2c0]      the host's window size (w | h << 32), 0 = the game's
              0xb5000068,   # cbnz x8,+12              set: on to the stur
              0xd2814008,   # mov x8,#0xa00            the game's 2560
              0xf2c0b408):  # movk x8,#0x5a0,lsl#32    and 1440
        emit(w)
    emit(B(here(), site + 8))   # back to stur x8,[x21,#0x14]
    fs_put(site, [B(site, start), 0xd503201f], 'boot window: the host\'s size (state +0x2c0, DM_DISPLAY_BUFFER docked), else the game\'s 2560x1440')
    ctx.capabilities.add('WINDOW_SIZE')

MATCH_FRAME_STEP = {'main': [
    {'name': 'frame ratio from the host\'s step', 'size': 0x9b4, 'fingerprints': ['6ae2aff5344d14568e4dbaf93455e2d8278384bf892ed6c6eca87fef98fbcd1d'], 'stub': frame_step,   # v131072 main+0x6e6be0
     'others': {'dynamic resolution': {'size': 0x294, 'fingerprints': ['7af6ceb0aedf8e0c17dc08ce17fcd6a7cba6d394a0d09e3b504c6d668dc418e7']},   # v131072 main+0x8065e0
                'dynamic resolution update': {'size': 0xb24, 'fingerprints': ['5a423697838976baf286cffa5e2ceef0d4e037abbcd9d371e90e9e702d61b3d4']},   # main+0x805aa0
                'window size': {'size': 0x570, 'fingerprints': ['f2c5558922a471ab585d374cc9293013d48da1562d43169367efdc8ea90a3fe8']},   # nnMain, main+0x1202ce0
                'gfx init': {'size': 0x2fc, 'fingerprints': ['f102ed9f80a4fc711650f4a86d11fe36602ecb330f422af96a4bad212dab5382']}}},   # main+0x1087b70
]}

BINDING = [
    {'what': 'frame ratio from the host\'s step', 'now': 'game', 'goal': 'game', 'purpose': 'frame rate',
     'why': "the game's own frame-ratio division, found by its function's fingerprint on any build that keeps the function",
     'checked': 'v131072 main: one function with this fingerprint, the site and its free registers read by disassembly (2026-11-08)'},
    {'what': 'dynamic resolution: full size, or a climb on the load measured at each level', 'now': 'game', 'goal': 'game', 'purpose': 'rendering',
     'why': "the game's own dynamic-resolution level function and update, found by their functions' fingerprints on any build that keeps both; switchable (DM_DYNAMIC_RESOLUTION)",
     'checked': 'v131072 main: one function with each fingerprint (the level function a leaf, x2..x11 / x16 / x17 / s0..s2 free), its callers, the update and the controller fields read by disassembly, the fields read in play (2026-11-08); the climb run natively against a model of the update and in play to full size (2026-11-09)'},
    {'what': 'boot window size from the host (DM_DISPLAY_BUFFER docked), else 2560x1440', 'now': 'game', 'goal': 'game', 'purpose': 'rendering',
     'why': "nnMain's constant window size, found by its function's fingerprint on any build that keeps the function; 0 in the state word keeps the game's",
     'checked': 'v131072 main: one function with this fingerprint, the two words at +0x200, no x16 / x17 in nnMain, no branch to +0x204 or +0x208, not rewrite sites, by disassembly (2026-11-16); in play: boot window 3840x2160, WindowInitialize 3840x2160 (ygy-75, 2026-11-16)'},
    {'what': 'graphics init: 3D base and crop (arg+8) from the host (DM_DISPLAY_BUFFER docked), else the game\'s', 'now': 'game', 'goal': 'game', 'purpose': 'rendering',
     'why': "a workaround at the value's consumer: the writer of the 2560x1440 at arg+8 is open; 0 in the state word keeps the game's",
     'checked': 'v131072 main: one function with this fingerprint, pacibsp at its entry, one caller (bl, x1 = the argument), arg+8 read as a w | h pair by both consumers, no x16 / x17, no branch to +4, by disassembly (2026-11-16); not run'},
]
