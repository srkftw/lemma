"""Decisive mutations of real compiler-produced Surface pre/post LLVM.

These are rejected host fixtures. They never construct a positive compiler AST,
execute guest policy, or stand in for an ordinary production artifact audit.
"""
from copy import deepcopy
import re
from core0_common import Core0Error
import surface_word_inline as target


def qualify(pre, post, unit):
    positives = {phase: target.validate(ir, unit, optimized=phase == 'post')
                 for phase, ir in [('pre', pre), ('post', post)]}
    rows = {row['source']: row for row in unit['functions']}
    bodies = {'pre': target._bodies(pre), 'post': target._bodies(post)}
    negatives = []

    def reject(name, ir, *, phase='post', independent=False, changed_unit=None):
        try:
            if independent:
                target._post_safety(ir, unit)
            else:
                target.validate(ir, unit if changed_unit is None else changed_unit, optimized=phase == 'post')
        except Core0Error as error:
            negatives.append({'name': name, 'phase': phase, 'independent_cfg_dataflow': independent,
                              'reason': str(error)})
            return
        raise Core0Error('actual Surface-word mutation admitted: ' + name)

    def change(name, source, old, new, *, phase='post', independent=False):
        ir = post if phase == 'post' else pre
        body = bodies[phase][rows[source]['symbol']]
        if body.count(old) != 1:
            raise Core0Error('mutation does not reach one actual instruction: ' + name)
        changed = ir.replace(body, body.replace(old, new, 1), 1)
        reject(name, changed, phase=phase, independent=independent)
        if independent:
            reject(name + '/complete-body', changed, phase=phase)

    load, copy = target.CALLERS; gather = target.GATHER
    callback = rows[target.CALLBACKS[0]]['symbol']
    for phase, sources in [('pre', (*target.CALLBACKS, load, copy, gather)), ('post', (load, copy, gather))]:
        for source in sources:
            body = bodies[phase][rows[source]['symbol']]
            # Every complete admitted owner has an actual constant in its body.
            match = re.search(r'(?<![A-Za-z0-9_.$%])(-?\d+)\b', body.split('\n', 1)[1])
            if match is None:
                raise Core0Error('actual body literal absent')
            old = match[0]; new = str(int(match[1]) ^ 1)
            # Use the exact first literal coordinate, preserving all other text.
            start = len(body.split('\n', 1)[0]) + 1 + match.start()
            altered = body[:start] + new + body[start+len(old):]
            reject(phase + '/complete-owner/' + source, (pre if phase == 'pre' else post).replace(body, altered, 1), phase=phase)
    for source in target.CALLBACKS:
        symbol = rows[source]['symbol']; body = bodies['pre'][symbol]
        reject('pre/callback-external/' + source, pre.replace(body, body.replace('define internal ', 'define ', 1), 1), phase='pre')
        reject('pre/callback-alwaysinline/' + source, pre.replace(body, body.replace(' nounwind {', ' nounwind alwaysinline {', 1), 1), phase='pre')
        reject('post/callback-restored/' + source, post + '\n' + body, phase='post')

    # Add a real direct LLVM call in the actual existing root as a rejected
    # fixture. All five pinned pre owners stay untouched, so the exhaustive
    # incoming-call gate itself must detect this new foreign caller.
    root_symbol = unit['roots'][0]['symbol']; root_body = bodies['pre'][root_symbol]
    call = '  %negative.foreign.callback = call { i64, i64 } @' + callback + '(i32 signext 0, i32 signext 64, i64 0, i64 0, i64 0, i64 0, i64 0)\n'
    require_entry = root_body.count('entry:\n') == 1
    if not require_entry:raise Core0Error('actual root entry absent')
    reject('pre/foreign-incoming-call', pre.replace(root_body, root_body.replace('entry:\n', 'entry:\n' + call, 1), 1), phase='pre')

    tile_mutants = [
        ('loop-start', '[ 0, %action.if.then.0 ]', '[ 1, %action.if.then.0 ]'),
        ('loop-extent', '%exitcond13.not = icmp eq i64 %indvars.iv.next, 64', '%exitcond13.not = icmp eq i64 %indvars.iv.next, 63'),
        ('loop-step', '%indvars.iv.next = add nuw nsw i64 %indvars.iv, 1', '%indvars.iv.next = add nuw nsw i64 %indvars.iv, 2'),
        ('row-coordinate', '%udiv51.i = lshr i64 %indvars.iv, 1', '%udiv51.i = lshr i64 %indvars.iv, 2'),
        ('row-stride', '%bin8.i = mul i64 %bin7.i, %udiv41', '%bin8.i = mul i64 %bin7.i, %arg2'),
        ('element-offset', '%urem17.i = shl nuw nsw i64 %indvars.iv, 3', '%urem17.i = shl nuw nsw i64 %indvars.iv, 2'),
        ('source-word-column', '%bin19.i = and i64 %urem17.i, 8', '%bin19.i = and i64 %urem17.i, 16'),
        ('source-coordinate', '%bin20.i = add i64 %bin14.i, %bin8.i', '%bin20.i = add i64 %bin14.i, %bin7.i'),
        ('destination-base', '%bin29.i = add nuw nsw i64 %urem17.i, 132352', '%bin29.i = add nuw nsw i64 %urem17.i, 132360'),
        ('value-field', '%action.call.value24.i = extractvalue { i64, i64 } %action.call.result21.i, 1', '%action.call.value24.i = extractvalue { i64, i64 } %action.call.result21.i, 0'),
        ('success-status', '%cmp25.i = icmp eq i64 %action.call.status-word22.i, 0', '%cmp25.i = icmp ne i64 %action.call.status-word22.i, 0'),
        ('fault-return', '%action.result.status-word36.i = and i64 %action.call.status-word22.i, 255', '%action.result.status-word36.i = and i64 %action.call.status-word22.i, 0'),
        ('volatile-write', 'store volatile i64 %action.call.value24.i', 'store i64 %action.call.value24.i'),
        ('write-value', 'store volatile i64 %action.call.value24.i', 'store volatile i64 %action.call.status-word22.i'),
        ('success-edge', 'br i1 %cmp25.i, label %' + callback + '.exit.thread, label %' + callback + '.exit', 'br i1 %cmp25.i, label %' + callback + '.exit, label %' + callback + '.exit.thread'),
    ]
    for name, old, new in tile_mutants:
        change('tile/' + name, load, old, new, independent=True)
    copy_mutants = [
        ('loop-start', '[ 0, %action.if.then.146 ]', '[ 1, %action.if.then.146 ]'),
        ('loop-extent', '%exitcond176.not = icmp eq i64 %indvars.iv.next, 64', '%exitcond176.not = icmp eq i64 %indvars.iv.next, 65'),
        ('loop-step', '%indvars.iv.next = add nuw nsw i64 %indvars.iv, 1', '%indvars.iv.next = add nuw nsw i64 %indvars.iv, 2'),
        ('word-offset', '%11 = shl nuw nsw i64 %indvars.iv, 3', '%11 = shl nuw nsw i64 %indvars.iv, 2'),
        ('tile-base', '%bin3.i = add nuw nsw i64 %11, 132352', '%bin3.i = add nuw nsw i64 %11, 132360'),
        ('packet-stride', '%bin296 = shl nuw nsw i64 %cast0, 9', '%bin296 = shl nuw nsw i64 %cast0, 8'),
        ('packet-base', '%bin297 = add nuw nsw i64 %bin296, 1089792', '%bin297 = add nuw nsw i64 %bin296, 1089800'),
        ('range-coordinate', '%.reass = add nuw nsw i64 %invariant.op, %11', '%.reass = add nuw nsw i64 %invariant.op, %cast0'),
        ('range-extent', '%or.cond.i.i = icmp samesign ult i64 %.reass, 1073676281', '%or.cond.i.i = icmp samesign ult i64 %.reass, 1073676282'),
        ('write-address', '%bin11.i = add nuw nsw i64 %bin297, %11', '%bin11.i = add nuw nsw i64 %bin297, %cast0'),
        ('write-value', 'store volatile i64 %execution.mem.0.loaded.5.i.i,', 'store volatile i64 %bin3.i,'),
        ('volatile-read', 'load volatile i64,', 'load i64,'),
        ('volatile-write', 'store volatile i64 %execution.mem.0.loaded.5.i.i,', 'store i64 %execution.mem.0.loaded.5.i.i,'),
        ('failed-range-status', '[ 7, %action.fold.body.152 ]', '[ 0, %action.fold.body.152 ]'),
        ('inverted-range', 'br i1 %or.cond.i.i, label %action.fold.latch.153, label %action.fold.outcome.156', 'br i1 %or.cond.i.i, label %action.fold.outcome.156, label %action.fold.latch.153'),
        ('load-check-order', '%execution.mem.0.loaded.5.i.i = load volatile i64, ptr %execution.mem.0.pointer.4.i6.i, align 8\n  %.reass = add nuw nsw i64 %invariant.op, %11\n  %or.cond.i.i = icmp samesign ult i64 %.reass, 1073676281', '%.reass = add nuw nsw i64 %invariant.op, %11\n  %or.cond.i.i = icmp samesign ult i64 %.reass, 1073676281\n  %execution.mem.0.loaded.5.i.i = load volatile i64, ptr %execution.mem.0.pointer.4.i6.i, align 8'),
    ]
    for name, old, new in copy_mutants:
        change('copy/' + name, copy, old, new, independent=True)
    for name, old, new in [
        ('alignment', '%urem1 = and i64 %arg0, 7', '%urem1 = and i64 %arg0, 3'),
        ('first-word-base', '%bin11 = and i64 %arg0, -8', '%bin11 = and i64 %arg0, -16'),
        ('aligned-bound', '%or.cond.i20 = icmp ult i64 %0, 1073676281', '%or.cond.i20 = icmp ule i64 %0, 1073676281'),
        ('first-bound', '%or.cond.i8 = icmp ult i64 %1, 1073676281', '%or.cond.i8 = icmp ult i64 %1, 1073676282'),
        ('second-bound', '%or.cond.i = icmp samesign ult i64 %2, 1073676281', '%or.cond.i = icmp samesign ult i64 %2, 1073676282'),
        ('second-address', '%bin21 = add nuw nsw i64 %bin11, 8', '%bin21 = add nuw nsw i64 %bin11, 16'),
        ('low-word-value', '%lshr32 = lshr i64 %execution.mem.0.loaded.5.i11, %bin30', '%lshr32 = lshr i64 %execution.mem.0.loaded.5.i, %bin30'),
        ('high-word-value', '%shl39 = shl i64 %execution.mem.0.loaded.5.i, %shift.count38', '%shl39 = shl i64 %execution.mem.0.loaded.5.i11, %shift.count38'),
        ('first-error', '[ 7, %action.if.else.4 ]', '[ 0, %action.if.else.4 ]'),
        ('second-error', '[ 7, %action.if.then.9 ]', '[ 0, %action.if.then.9 ]'),
        ('second-before-first-bound', 'br i1 %or.cond.i8, label %action.if.then.9, label %action.if.merge.5', 'br i1 %or.cond.i8, label %action.if.then.15, label %action.if.merge.5'),
    ]:
        change('gather/' + name, gather, old, new, independent=True)
    for key, value in [('configuration', 'lemmasim-silicon-closure-entry2-bulk-notebook'),
                       ('role', 'kernel'), ('contract_version', 'core0-user-v0.1'), ('image_key', 'course')]:
        changed = deepcopy(unit); changed[key] = value
        reject('metadata/' + key, post, changed_unit=changed)
    changed = deepcopy(unit); changed[target.FIELD]['callbacks'][0]['symbol'] = rows[load]['symbol']
    reject('metadata/foreign-exemption', post, changed_unit=changed)
    return {'positives': positives, 'negative_count': len(negatives), 'negatives': negatives,
            'independent_cfg_dataflow_negatives': sum(n['independent_cfg_dataflow'] for n in negatives)}
