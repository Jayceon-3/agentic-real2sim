"""Sequential, restartable Blender stages with explicit per-candidate operation logs."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback

SOURCE = Path(__file__).resolve().parent
RUN = SOURCE.parent
spec = importlib.util.spec_from_file_location('batch_stage', SOURCE / 'blender_stage.py')
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--phase', choices=['development', 'evaluation'], required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
    names = [f'{obj}-seed-{seed}' for obj in ['cabinet', 'chair'] for seed in [42, 43, 44]]
    if not all((RUN / 'placements' / (name + '.json')).is_file() for name in names):
        raise ValueError('All six placements must exist before the Blender batch')
    tasks = ['import', 'alignment', 'diagnostics'] if args.phase == 'development' else ['evaluation']
    journal = {'phase': args.phase, 'status': 'running', 'tasks': []}
    journal_path = RUN / 'logs' / (args.phase + '-batch.json')
    start = time.perf_counter()
    try:
        for name in names:
            scene_folder = RUN / 'scenes' / (name + '-final')
            for task in tasks:
                existing = (scene_folder / 'non_target_invariants.json' if task == 'import'
                            else scene_folder / 'target_placement_summary.json' if task == 'diagnostics'
                            else RUN / 'renders' / task / name / 'render.json')
                if existing.is_file():
                    previous = json.loads(existing.read_text())
                    if task == 'diagnostics' or previous.get('status') in ['completed', 'passed']:
                        journal['tasks'].append({'candidate': name, 'stage': task, 'status': 'existing_completed'})
                        continue
                row = {'candidate': name, 'stage': task, 'status': 'running'}
                journal['tasks'].append(row)
                stage.tool.write(journal_path, journal)
                sys.argv = [str(SOURCE / 'blender_stage.py'), '--', '--stage', task, '--candidate', name]
                before = time.perf_counter()
                stage.main()
                row.update(status='completed', wall_seconds=time.perf_counter() - before)
                stage.tool.write(journal_path, journal)
        journal['status'] = 'completed'
    except BaseException:
        journal['status'] = 'failed'
        if journal['tasks']:
            journal['tasks'][-1]['status'] = 'failed'
        (RUN / 'logs' / (args.phase + '-failure.txt')).write_text(traceback.format_exc())
        raise
    finally:
        journal['wall_seconds'] = time.perf_counter() - start
        stage.tool.write(journal_path, journal)


if __name__ == '__main__':
    main()
