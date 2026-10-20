#!/usr/bin/env python3
"""Pinned paused/prelaunch lifecycle only for raw-UART logical2 restore."""
import argparse
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('source',type=Path)
a=p.parse_args()
path=a.source/'migration/savevm.c'
s=path.read_text()
boundary = '        (runstate_get() != RUN_STATE_PAUSED && runstate_get() != RUN_STATE_PRELAUNCH) ||'
if s.count(boundary) != 1:
    raise SystemExit('logical2 incoming boundary absent/ambiguous')
s = s.replace(boundary, '''        (runstate_get() != RUN_STATE_PAUSED && runstate_get() != RUN_STATE_PRELAUNCH &&
         !(runstate_get() == RUN_STATE_INMIGRATE &&
           object_dynamic_cast(OBJECT(qdev_get_machine()),
             MACHINE_TYPE_NAME("lemma-silicon-fast-softtlb")))) ||''')
boundary = '            if (runstate_get() != RUN_STATE_PRELAUNCH) {'
if s.count(boundary) != 1:
    raise SystemExit('logical2 saved lifecycle absent/ambiguous')
s = s.replace(boundary, '''            if (runstate_get() == RUN_STATE_INMIGRATE &&
                object_dynamic_cast(OBJECT(qdev_get_machine()),
                    MACHINE_TYPE_NAME("lemma-silicon-fast-softtlb"))) {
                runstate_set(global_state_get_runstate());
            } else if (runstate_get() != RUN_STATE_PRELAUNCH) {''')
boundary = '    runstate_set(RUN_STATE_PAUSED);\n}\n'
if s.count(boundary) != 1:
    raise SystemExit('logical2 post-adoption lifecycle absent/ambiguous')
s = s.replace(boundary, '''    if (!runstate_check(RUN_STATE_PRELAUNCH) && !runstate_check(RUN_STATE_PAUSED)) {
        runstate_set(RUN_STATE_PAUSED);
    }
}
''')
path.write_text(s)
